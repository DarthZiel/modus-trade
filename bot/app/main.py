import asyncio
import io
import logging
import os
from collections import defaultdict
from uuid import NAMESPACE_URL, uuid4, uuid5

import httpx
from aiogram import Bot, Dispatcher, F
from aiogram.exceptions import (
    TelegramAPIError,
    TelegramForbiddenError,
    TelegramRetryAfter,
)
from aiogram.filters import Command, CommandStart
from aiogram.filters.command import CommandObject
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    WebAppInfo,
)

logger = logging.getLogger(__name__)
dispatcher = Dispatcher()
locks = defaultdict(asyncio.Lock)
STATUSES = {
    "received": "Получено",
    "reviewing": "На рассмотрении",
    "needs_info": "Нужно уточнение",
    "in_progress": "В работе",
    "awaiting_confirmation": "Подтвердите результат",
    "closed": "Закрыто",
    "rejected": "Отклонено",
}


class BackendError(Exception):
    pass


class Backend:
    def __init__(self, url, secret):
        self.client = httpx.AsyncClient(
            base_url=url,
            headers={"X-Bot-Secret": secret, "X-Modus-Request": "1"},
            timeout=60,
        )

    async def call(self, method, path, telegram_id=None, **kwargs):
        try:
            result = await self.client.request(
                method,
                path,
                headers={"X-Telegram-Id": str(telegram_id)} if telegram_id else {},
                **kwargs,
            )
        except httpx.HTTPError:
            raise BackendError(
                "Сервис недоступен. Черновик сохранён; повторите действие позже."
            ) from None
        if result.is_error:
            detail = (
                result.json().get("detail")
                if result.headers.get("content-type", "").startswith("application/json")
                else None
            )
            raise BackendError(
                detail
                if isinstance(detail, str) and result.status_code < 500
                else "Не удалось выполнить действие. Проверьте данные или повторите позже."
            )
        return None if result.status_code == 204 else result.json()


backend: Backend
mini_url = ""


def keyboard(rows):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=label, callback_data=value)
                for label, value in row
            ]
            for row in rows
        ]
    )


def app_button(path="/appeals"):
    return InlineKeyboardButton(
        text="Открыть кабинет", web_app=WebAppInfo(url=f"{mini_url}/mini{path}")
    )


def menu():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Сообщить о проблеме", callback_data="new:problem"
                )
            ],
            [InlineKeyboardButton(text="Предложить идею", callback_data="new:idea")],
            [InlineKeyboardButton(text="Продолжить черновик", callback_data="resume")],
            [
                InlineKeyboardButton(text="Мои обращения", callback_data="list:1"),
                app_button(),
            ],
        ]
    )


async def state(telegram_id, value=None):
    if value is None:
        return (await backend.call("GET", "/internal/telegram/state", telegram_id))[
            "value"
        ]
    await backend.call(
        "PUT", "/internal/telegram/state", telegram_id, json={"value": value}
    )


async def show_card(message, telegram_id, appeal_id):
    item = await backend.call("GET", f"/appeals/{appeal_id}", telegram_id)
    is_author = (
        item["author_id"] == (await backend.call("GET", "/auth/me", telegram_id))["id"]
    )
    path = f"/appeals/{appeal_id}" if is_author else f"/queue/{appeal_id}"
    buttons = [
        [
            InlineKeyboardButton(
                text="Ответить по обращению", callback_data=f"reply:{appeal_id}"
            )
        ],
        [app_button(path)],
    ]
    if item["status"] == "awaiting_confirmation" and is_author:
        buttons.insert(
            0,
            [
                InlineKeyboardButton(
                    text="Помогло",
                    callback_data=f"help:{appeal_id}:{item['assignment_version']}",
                ),
                InlineKeyboardButton(
                    text="Проблема осталась",
                    callback_data=f"reopen:{appeal_id}:{item['assignment_version']}",
                ),
            ],
        )
    text = f"{item['number']} · {STATUSES[item['status']]}\n{item['title']}\nОтветственный: {item['responsible'] or 'ещё не назначен'}"
    if item["result"]:
        text += "\n\nРезультат:\n" + item["result"][:2200]
    await message.answer(
        text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )


@dispatcher.message(CommandStart(), F.chat.type == "private")
async def start(message: Message, command: CommandObject):
    try:
        if command.args and command.args.startswith("link_"):
            user = await backend.call(
                "POST",
                "/internal/telegram/bind",
                json={"token": command.args[5:], "telegram_id": message.from_user.id},
            )
            await message.answer(
                f"Telegram привязан к аккаунту {user['name']}. Пароль в боте не нужен.",
                reply_markup=menu(),
            )
        else:
            await backend.call("GET", "/auth/me", message.from_user.id)
            await message.answer(
                "Выберите действие. /cancel — отменить черновик или ответ.",
                reply_markup=menu(),
            )
    except BackendError as error:
        await message.answer(
            str(error)
            + "\nВойдите на сайт по приглашению → Telegram → Привязать Telegram."
        )


@dispatcher.message(Command("cancel"), F.chat.type == "private")
async def cancel(message: Message):
    try:
        await state(message.from_user.id, {})
        await message.answer("Черновик или ответ отменён.", reply_markup=menu())
    except BackendError as error:
        await message.answer(str(error))


@dispatcher.message(Command("help"), F.chat.type == "private")
async def help_command(message: Message):
    await message.answer(
        "/start — меню, /cancel — отмена. Отправляйте обращения через меню. Для ответа сначала выберите обращение. Привязка и отключение Telegram доступны на сайте."
    )


async def similar_hint(uid, draft):
    """Existing appeals with the same situation; a hint that never blocks filing."""
    try:
        items = await backend.call(
            "POST",
            "/similar",
            uid,
            json={
                "title": draft["title"][:160],
                "description": draft["description"][:2000],
                "kind": draft["kind"],
            },
        )
    except BackendError:
        return "", []
    if not isinstance(items, list) or not items:
        return "", []
    lines, rows = ["\n\nПохоже, об этом уже сообщали:"], []
    for item in items[:3]:
        status = STATUSES.get(item["status"], item["status"])
        lines.append(f"• {item['number']} · {status} — {item['title'][:80]}")
        if item.get("can_join"):
            rows.append(
                [(f"У меня то же — присоединиться к {item['number']}", f"join:{item['id']}")]
            )
        elif item.get("relation") == "own":
            lines.append("  Это ваше обращение — дополните его ответом в карточке.")
        elif item.get("relation") == "supported":
            lines.append("  Вы уже присоединились к нему.")
    lines.append(
        "Присоединитесь вместо нового обращения — ответственный увидит, что это касается не только вас."
    )
    return "\n".join(lines), rows


async def preview(message, draft, uid=None):
    hint, join_rows = await similar_hint(uid, draft) if uid else ("", [])
    await message.answer(
        f"Проверьте обращение\n\n{draft['title']}\n\n{draft['description'][:2900]}\n\nВложений: {len(draft.get('files', []))}. Категория: {draft.get('category', 'other')}.\nПолный текст сохранён; категорию и заголовок можно задать в Mini App.{hint}",
        reply_markup=keyboard(
            join_rows
            + [
                [
                    (
                        "Отправить обращение"
                        if draft.get("original_description")
                        else "Отправить исходный текст",
                        f"submit:{draft['submission_id']}",
                    )
                ],
                [("Исправить", "edit"), ("Отменить", "cancel")],
                [("Убрать вложения", "clear-files"), ("Помочь сформулировать", "ai")],
            ]
        ),
    )


async def ai_proposal(message, uid, draft):
    result = await backend.call(
        "POST",
        "/ai/appeal",
        uid,
        json={
            "kind": draft["kind"],
            "description": draft["description"],
            "answers": draft.get("ai_answers", []),
        },
    )
    draft["ai_proposal"] = result["suggestion"]
    draft["ai_source"] = draft["description"]
    draft["ai_id"] = str(uuid4())
    draft["mode"] = "draft"
    await state(uid, draft)
    value = result["suggestion"]
    rows = [
        [("Проверил — применить", f"ai-apply:{draft['ai_id']}")],
        [("Оставить мой текст", "resume")],
    ]
    if value["questions"]:
        rows.insert(0, [("Ответить на уточнения", f"ai-answers:{draft['ai_id']}")])
    label = (
        "Демо: локальные шаблоны, без ИИ-модели."
        if result["mode"] == "demo"
        else "Предложение ИИ — проверьте факты."
    )
    await message.answer(
        f"{label}\n\n{value['title']}\n\n{value['description'][:2000]}",
        reply_markup=keyboard(rows),
    )


class LimitedBuffer(io.BytesIO):
    def write(self, data):
        if self.tell() + len(data) > 10 * 1024 * 1024:
            raise BackendError(
                "Файл больше 10 МБ. Удалите черновик или отправьте обращение через Mini App."
            )
        return super().write(data)


async def send_reply(message, uid, draft, body):
    """Reply or return-to-work comment for the appeal the user opened."""
    if not 1 <= len(body) <= 10000:
        raise BackendError("Отправьте текст от 1 до 10 000 символов.")
    appeal_id = draft["appeal_id"]
    payload = {
        "client_id": str(
            uuid5(NAMESPACE_URL, f"tg-message:{uid}:{draft.get('message_key', message.message_id)}")
        )
    }
    if draft["mode"] == "reply":
        await backend.call(
            "POST",
            f"/appeals/{appeal_id}/messages",
            uid,
            json={**payload, "body": body},
        )
    else:
        await backend.call(
            "POST",
            f"/appeals/{appeal_id}/feedback",
            uid,
            json={
                **payload,
                "outcome": "reopen",
                "comment": body,
                "expected_version": draft["expected_version"],
            },
        )
    await state(uid, {})
    await message.answer(f"Ответ по MT-{appeal_id:06} сохранён.", reply_markup=menu())


async def apply_description(message, uid, draft, description):
    if not 10 <= len(description) <= 10000:
        raise BackendError("Описание должно содержать от 10 до 10 000 символов.")
    if draft.get("description") and not draft.get("editing"):
        raise BackendError(
            "Чтобы заменить описание, нажмите «Исправить» в предпросмотре."
        )
    draft.update(
        description=description,
        title=(
            " ".join(description.split())[:160]
            if len(" ".join(description.split())) >= 5
            else "Обращение сотрудника"
        ),
        editing=False,
    )


async def ask_voice(message, uid, draft, voice):
    """Voice goes to an external model only after an explicit tap."""
    info = await backend.call("GET", "/ai/status", uid)
    if not info.get("voice"):
        raise BackendError(
            "Голосовые пока не распознаются. Отправьте, пожалуйста, текстом."
        )
    if voice.file_size and voice.file_size > 4 * 1024 * 1024:
        raise BackendError("Голосовое слишком длинное. Уложитесь в 2–3 минуты.")
    draft["pending_voice"] = {
        "file_id": voice.file_id,
        "mime": getattr(voice, "mime_type", None) or "audio/ogg",
        "key": message.message_id,
    }
    await state(uid, draft)
    await message.answer(
        "Расшифровать голосовое? Запись будет передана сервису OpenRouter и "
        "провайдеру модели распознавания. Профиль и вложения не передаются.",
        reply_markup=keyboard(
            [[("Расшифровать", "voice-ok")], [("Напишу текстом", "voice-no")]]
        ),
    )


async def transcribe_pending(message, uid, draft):
    pending = draft.get("pending_voice")
    if not pending:
        raise BackendError("Голосовое не найдено. Отправьте его ещё раз.")
    content = LimitedBuffer()
    await message.bot.download(pending["file_id"], destination=content)
    result = await backend.call(
        "POST",
        "/ai/transcribe",
        uid,
        files={"file": ("voice.ogg", content.getvalue(), pending["mime"])},
    )
    return result["text"], pending


async def process_callback(query: CallbackQuery):
    uid = query.from_user.id
    message = query.message
    data = query.data or ""
    await backend.call("GET", "/auth/me", uid)
    if data.startswith("new:"):
        previous = await state(uid)
        if previous.get("mode") == "draft" and previous.get("description"):
            raise BackendError(
                "У вас есть сохранённый черновик. Нажмите «Продолжить черновик» или /cancel перед новым обращением."
            )
        kind = data.split(":")[1]
        if kind not in {"problem", "idea"}:
            return
        await state(
            uid,
            {"mode": "draft", "kind": kind, "submission_id": str(uuid4()), "files": []},
        )
        await message.answer(
            "Опишите проблему или идею одним сообщением — текстом или голосовым (от 10 до 10 000 символов). Затем можно добавить до 5 фото или документов PDF, JPG, PNG, WebP по 10 МБ. /cancel — отменить."
        )
    elif data.startswith("list:"):
        page = max(1, min(int(data.split(":")[1]), 100000))
        result = await backend.call("GET", f"/appeals?page={page}&page_size=5", uid)
        buttons = [
            [
                InlineKeyboardButton(
                    text=f"{x['number']} · {x['title'][:40]}",
                    callback_data=f"card:{x['id']}",
                )
            ]
            for x in result["items"]
        ]
        paging = []
        if page > 1:
            paging.append(
                InlineKeyboardButton(text="Назад", callback_data=f"list:{page - 1}")
            )
        if page * 5 < result["total"]:
            paging.append(
                InlineKeyboardButton(text="Далее", callback_data=f"list:{page + 1}")
            )
        if paging:
            buttons.append(paging)
        await message.answer(
            "Ваши обращения" if result["items"] else "У вас пока нет обращений.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
            if buttons
            else menu(),
        )
    elif data.startswith("card:"):
        await show_card(message, uid, int(data.split(":")[1]))
    elif data.startswith(("reply:", "reopen:")):
        parts = data.split(":")
        appeal_id = int(parts[1])
        await backend.call("GET", f"/appeals/{appeal_id}", uid)
        await state(
            uid,
            {
                "mode": parts[0],
                "appeal_id": appeal_id,
                "expected_version": int(parts[2]) if len(parts) > 2 else None,
            },
        )
        await message.answer(
            f"MT-{appeal_id:06}: "
            + (
                "опишите, почему проблема осталась."
                if parts[0] == "reopen"
                else "отправьте текст ответа одним сообщением."
            )
            + " /cancel — отменить."
        )
    elif data.startswith("help:"):
        _, appeal_id, version = data.split(":")
        await backend.call(
            "POST",
            f"/appeals/{int(appeal_id)}/feedback",
            uid,
            json={
                "client_id": str(
                    uuid5(NAMESPACE_URL, f"tg-help:{uid}:{appeal_id}:{version}")
                ),
                "expected_version": int(version),
                "outcome": "helped",
                "comment": "",
            },
        )
        await message.answer(
            "Результат подтверждён. Обращение закрыто.", reply_markup=menu()
        )
    elif data in {"resume", "clear-files"}:
        draft = await state(uid)
        if draft.get("mode") != "draft" or not draft.get("description"):
            raise BackendError(
                "Нет готового черновика. Выберите тип обращения и отправьте описание."
            )
        draft["mode"] = "draft"
        await state(uid, draft)
        if data == "clear-files":
            draft["files"] = []
            await state(uid, draft)
        await preview(message, draft, uid)
    elif data == "cancel":
        await state(uid, {})
        await message.answer("Черновик отменён.", reply_markup=menu())
    elif data == "ai" or data.startswith("ai-consent:") or data == "ai-consent":
        draft = await state(uid)
        if draft.get("mode") != "draft" or not draft.get("description"):
            raise BackendError("Сначала подготовьте описание обращения.")
        info = await backend.call("GET", "/ai/status", uid)
        if not info["available"]:
            raise BackendError("ИИ не подключён. Можно отправить исходный текст.")
        if (
            info["mode"] in {"openai", "openrouter"}
            and data != f"ai-consent:{info['mode']}"
        ):
            await message.answer(
                f"Для подготовки предложения описание и ваши уточнения будут переданы сервису {'OpenRouter и провайдеру выбранной модели' if info['mode'] == 'openrouter' else 'OpenAI'}. Вложения и профиль не передаются.",
                reply_markup=keyboard(
                    [
                        [("Разрешаю передать текст", f"ai-consent:{info['mode']}")],
                        [("Продолжить без ИИ", "resume")],
                    ]
                ),
            )
            return
        draft["ai_answers"] = []
        await ai_proposal(message, uid, draft)
    elif data.startswith(("ai-apply:", "ai-answers:")):
        draft = await state(uid)
        if data.split(":")[1] != draft.get("ai_id") or draft.get(
            "ai_source"
        ) != draft.get("description"):
            raise BackendError("Предложение устарело. Подготовьте его заново.")
        proposal = draft["ai_proposal"]
        if data.startswith("ai-apply:"):
            draft["original_description"] = (
                draft.get("original_description") or draft["description"]
            )
            draft.update(
                {key: proposal[key] for key in ["title", "description", "category"]}
            )
            draft["mode"] = "draft"
            await state(uid, draft)
            await preview(message, draft, uid)
        elif proposal["questions"]:
            draft.update(mode="ai_answers", ai_answers=[])
            await state(uid, draft)
            await message.answer(
                proposal["questions"][0]
                + "\n/cancel — отменить черновик; кнопка «Оставить мой текст» вернёт предпросмотр."
            )
    elif data == "voice-no":
        draft = await state(uid)
        draft.pop("pending_voice", None)
        await state(uid, draft)
        await message.answer("Хорошо, отправьте описание текстом.")
    elif data == "voice-ok":
        draft = await state(uid)
        await message.answer("Расшифровываю…")
        text, pending = await transcribe_pending(message, uid, draft)
        draft.pop("pending_voice", None)
        if draft.get("mode") == "draft":
            await apply_description(message, uid, draft, text)
            draft["voice"] = True
            await state(uid, draft)
            await message.answer(f"Распознал голосовое:\n«{text[:1500]}»")
            await preview(message, draft, uid)
        elif draft.get("mode") in {"reply", "reopen"}:
            draft.update(voice_text=text, message_key=f"voice-{pending['key']}")
            await state(uid, draft)
            await message.answer(
                f"Распознал:\n«{text[:1500]}»\n\nОтправить как ответ по MT-{draft['appeal_id']:06}?",
                reply_markup=keyboard(
                    [[("Отправить ответ", "voice-send")], [("Напишу текстом", "voice-no")]]
                ),
            )
        else:
            raise BackendError("Сначала выберите действие в меню.")
    elif data == "voice-send":
        draft = await state(uid)
        if draft.get("mode") not in {"reply", "reopen"} or not draft.get("voice_text"):
            raise BackendError("Эта кнопка устарела. Откройте обращение заново.")
        await send_reply(message, uid, draft, draft["voice_text"])
    elif data.startswith("join:"):
        appeal_id = int(data.split(":")[1])
        draft = await state(uid)
        view = await backend.call(
            "POST", f"/appeals/{appeal_id}/support", uid, json={"comment": ""}
        )
        if draft.get("mode") == "draft":
            await state(uid, {})
        await message.answer(
            f"Вы присоединились к {view['number']}: «{view['title']}».\n"
            "Черновик не отправлен — дубль не нужен. Мы сообщим, когда обращение "
            "примут в работу и когда появится результат.",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[app_button(f"/appeals/{appeal_id}")]]
            ),
        )
    elif data == "edit":
        draft = await state(uid)
        if draft.get("mode") != "draft":
            raise BackendError("Черновик уже отправлен или отменён.")
        draft["editing"] = True
        await state(uid, draft)
        await message.answer("Отправьте исправленное описание. Вложения сохранятся.")
    elif data.startswith("submit:"):
        draft = await state(uid)
        if (
            draft.get("mode") != "draft"
            or not draft.get("description")
            or data[7:] != draft.get("submission_id")
        ):
            raise BackendError(
                "Эта кнопка относится к старому черновику. Откройте актуальное меню."
            )
        files = [
            (name, (None, str(draft[name])))
            for name in ["kind", "title", "description", "submission_id"]
        ]
        files.append(("category", (None, draft.get("category", "other"))))
        if draft.get("original_description"):
            files.append(
                ("original_description", (None, draft["original_description"]))
            )
        for attachment in draft.get("files", []):
            content = LimitedBuffer()
            await message.bot.download(attachment["file_id"], destination=content)
            files.append(
                ("files", (attachment["name"], content.getvalue(), attachment["mime"]))
            )
        item = await backend.call("POST", "/appeals", uid, files=files)
        await state(uid, {})
        await message.answer(f"Обращение отправлено: {item['number']}")
        await show_card(message, uid, item["id"])


@dispatcher.callback_query()
async def callback(query: CallbackQuery):
    if not query.message or query.message.chat.type != "private":
        await query.answer("Доступно только в личном чате", show_alert=True)
        return
    await query.answer()
    async with locks[query.from_user.id]:
        try:
            await process_callback(query)
        except (BackendError, ValueError) as error:
            await query.message.answer(
                str(error)
                if isinstance(error, BackendError)
                else "Эта кнопка устарела. Откройте /start."
            )
        except (httpx.HTTPError, TelegramAPIError):
            await query.message.answer(
                "Не удалось загрузить данные. Черновик сохранён; повторите позже."
            )


@dispatcher.message(F.chat.type == "private")
async def incoming(message: Message):
    uid = message.from_user.id
    async with locks[uid]:
        try:
            draft = await state(uid)
            mode = draft.get("mode")
            voice = message.voice or message.audio
            if voice:
                if mode not in {"draft", "reply", "reopen"}:
                    raise BackendError(
                        "Сначала выберите действие: «Сообщить о проблеме», «Предложить идею» или ответ в карточке."
                    )
                if mode == "draft" and draft.get("description") and not draft.get("editing"):
                    raise BackendError(
                        "Чтобы заменить описание голосом, нажмите «Исправить» в предпросмотре."
                    )
                await ask_voice(message, uid, draft, voice)
                return
            if mode == "ai_answers":
                body = (message.text or "").strip()
                if not 1 <= len(body) <= 2000:
                    raise BackendError("Ответьте текстом от 1 до 2000 символов.")
                questions = draft["ai_proposal"]["questions"]
                draft["ai_answers"].append(
                    {"question": questions[len(draft["ai_answers"])], "answer": body}
                )
                if len(draft["ai_answers"]) < len(questions):
                    await state(uid, draft)
                    await message.answer(questions[len(draft["ai_answers"])])
                else:
                    draft["mode"] = "draft"
                    await state(uid, draft)
                    await ai_proposal(message, uid, draft)
                return
            if mode in {"reply", "reopen"}:
                draft.pop("message_key", None)
                await send_reply(message, uid, draft, (message.text or "").strip())
                return
            if mode != "draft":
                await message.answer(
                    "Сначала выберите действие. Для ответа откройте конкретное обращение.",
                    reply_markup=menu(),
                )
                return
            if message.text:
                await apply_description(message, uid, draft, message.text.strip())
            elif message.photo or message.document:
                if not draft.get("description"):
                    raise BackendError(
                        "Сначала отправьте описание отдельным текстовым сообщением."
                    )
                if len(draft.get("files", [])) >= 5:
                    raise BackendError("В черновике уже 5 вложений.")
                attachment = message.photo[-1] if message.photo else message.document
                if (
                    attachment.file_size is None
                    or attachment.file_size > 10 * 1024 * 1024
                ):
                    raise BackendError("Максимальный размер файла — 10 МБ.")
                name = (
                    f"photo-{message.message_id}.jpg"
                    if message.photo
                    else attachment.file_name or "document"
                )
                draft["files"].append(
                    {
                        "file_id": attachment.file_id,
                        "name": name,
                        "mime": "image/jpeg"
                        if message.photo
                        else attachment.mime_type or "application/octet-stream",
                    }
                )
            else:
                raise BackendError(
                    "Поддерживаются текст, голосовые, фото и документы PDF, JPG, PNG, WebP."
                )
            await state(uid, draft)
            await preview(message, draft, uid)
        except BackendError as error:
            await message.answer(str(error))


async def deliver(bot):
    while True:
        try:
            jobs = await backend.call("POST", "/internal/telegram/deliveries")
            for job in jobs:
                outcome = "retry"
                try:
                    await bot.send_message(
                        job["telegram_id"],
                        job["text"],
                        reply_markup=InlineKeyboardMarkup(
                            inline_keyboard=[
                                [
                                    InlineKeyboardButton(
                                        text="Открыть обращение",
                                        web_app=WebAppInfo(url=job["url"]),
                                    )
                                ],
                                [
                                    InlineKeyboardButton(
                                        text="Краткая карточка / ответ",
                                        callback_data=f"card:{job['appeal_id']}",
                                    )
                                ],
                            ]
                        ),
                    )
                    outcome = "sent"
                except TelegramForbiddenError:
                    outcome = "blocked"
                except TelegramRetryAfter as error:
                    await asyncio.sleep(min(error.retry_after, 60))
                except TelegramAPIError:
                    logger.warning("Telegram delivery failed; retry scheduled")
                await backend.call(
                    "POST",
                    f"/internal/telegram/deliveries/{job['id']}",
                    json={"claim": job["claim"], "outcome": outcome},
                )
        except BackendError:
            logger.warning("Backend unavailable for notifications; retry scheduled")
        await asyncio.sleep(15)


async def main():
    global backend, mini_url
    token = os.getenv("BOT_TOKEN", "").strip()
    secret = os.getenv("BOT_API_SECRET", "").strip()
    mini_url = os.getenv("MINI_APP_URL", "").rstrip("/")
    if not token or len(secret) < 32 or not mini_url.startswith("https://"):
        raise SystemExit(
            "Заполните BOT_TOKEN, BOT_API_SECRET (минимум 32 символа), MINI_APP_URL (HTTPS) в .env."
        )
    backend = Backend(os.getenv("BACKEND_URL", "http://backend:8000"), secret)
    logging.basicConfig(level=logging.INFO)
    async with Bot(token=token) as bot:
        task = asyncio.create_task(deliver(bot))
        try:
            await dispatcher.start_polling(
                bot, allowed_updates=["message", "callback_query"]
            )
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            await backend.client.aclose()


if __name__ == "__main__":
    asyncio.run(main())
