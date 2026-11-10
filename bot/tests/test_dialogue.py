import asyncio
from copy import deepcopy
from types import SimpleNamespace

import pytest
from app import main


class FakeBackend:
    def __init__(self):
        self.saved = {}
        self.calls = []
        self.fail_submit = False

    async def call(self, method, path, telegram_id=None, **kwargs):
        self.calls.append((method, path, telegram_id, deepcopy(kwargs)))
        if path == "/auth/me":
            return {"id": "author-id"}
        if path == "/internal/telegram/state":
            if method == "PUT":
                self.saved[telegram_id] = deepcopy(kwargs["json"]["value"])
            return {"value": deepcopy(self.saved.get(telegram_id, {}))}
        if path == "/appeals" and method == "POST":
            if self.fail_submit:
                raise main.BackendError("Нет соединения")
            return {"id": 17, "number": "MT-000017"}
        if path == "/appeals/17":
            return {
                "id": 17,
                "number": "MT-000017",
                "title": "Полки без маркировки",
                "status": "awaiting_confirmation",
                "author_id": "author-id",
                "responsible": "Иван",
                "result": "Полки подписаны",
                "assignment_version": 4,
            }
        return {}


class FakeMessage:
    def __init__(self, uid=5000000001, text=None, message_id=19):
        self.from_user = SimpleNamespace(id=uid)
        self.chat = SimpleNamespace(type="private")
        self.message_id = message_id
        self.text = text
        self.photo = None
        self.document = None
        self.voice = None
        self.audio = None
        self.answers = []
        self.bot = SimpleNamespace(download=self.download)

    async def answer(self, text, **kwargs):
        self.answers.append((text, kwargs))

    async def download(self, file_id, destination):
        destination.write(b"file-bytes")


def query(message, data):
    return SimpleNamespace(from_user=message.from_user, message=message, data=data)


@pytest.fixture()
def backend(monkeypatch):
    fake = FakeBackend()
    monkeypatch.setattr(main, "backend", fake, raising=False)
    monkeypatch.setattr(main, "mini_url", "https://modus.example.com")
    main.locks.clear()
    return fake


def test_draft_preview_edit_attachment_clear_and_submit(backend):
    async def scenario():
        message = FakeMessage()
        await main.process_callback(query(message, "new:problem"))
        message.text = "На складе похожие коробки лежат без маркировки."
        await main.incoming(message)
        draft = backend.saved[message.from_user.id]
        assert draft["description"] == message.text and draft["kind"] == "problem"
        assert "Проверьте обращение" in message.answers[-1][0]
        message.text = None
        message.photo = [SimpleNamespace(file_id="photo-id", file_size=128)]
        await main.incoming(message)
        assert len(backend.saved[message.from_user.id]["files"]) == 1
        await main.process_callback(query(message, "clear-files"))
        assert backend.saved[message.from_user.id]["files"] == []
        await main.process_callback(query(message, "edit"))
        message.photo = None
        message.text = "Нужны подписи на полках с похожими коробками."
        await main.incoming(message)
        assert backend.saved[message.from_user.id]["description"] == message.text
        await main.process_callback(query(message, "submit:" + draft["submission_id"]))
        assert backend.saved[message.from_user.id] == {}
        submit = next(
            call for call in backend.calls if call[:2] == ("POST", "/appeals")
        )
        fields = {name: value[1] for name, value in submit[3]["files"]}
        assert (
            fields["description"] == message.text
            and fields["submission_id"] == draft["submission_id"]
        )
        assert "MT-000017" in message.answers[-1][0]

    asyncio.run(scenario())


def test_failed_submit_preserves_draft_and_stable_id(backend):
    async def scenario():
        message = FakeMessage(text="На складе не хватает маркировки полок.")
        await main.process_callback(query(message, "new:idea"))
        await main.incoming(message)
        draft = deepcopy(backend.saved[message.from_user.id])
        backend.fail_submit = True
        with pytest.raises(main.BackendError):
            await main.process_callback(
                query(message, "submit:" + draft["submission_id"])
            )
        assert backend.saved[message.from_user.id] == draft
        backend.fail_submit = False
        await main.process_callback(query(message, "submit:" + draft["submission_id"]))
        submits = [call for call in backend.calls if call[:2] == ("POST", "/appeals")]
        assert submits[0][3] == submits[1][3]

    asyncio.run(scenario())


def test_reply_context_and_return_comment(backend):
    async def scenario():
        message = FakeMessage(text="Коробки путают на второй полке.")
        await main.process_callback(query(message, "reply:17"))
        await main.incoming(message)
        sent = next(call for call in backend.calls if call[1] == "/appeals/17/messages")
        assert sent[3]["json"]["body"] == message.text
        await main.process_callback(query(message, "reopen:17:4"))
        await main.incoming(message)
        returned = next(
            call for call in backend.calls if call[1] == "/appeals/17/feedback"
        )
        assert returned[3]["json"]["expected_version"] == 4
        assert returned[3]["json"]["comment"] == message.text
        assert returned[3]["json"]["outcome"] == "reopen"
        assert backend.saved[message.from_user.id] == {}

    asyncio.run(scenario())


def test_confirmation_buttons_are_idempotent(backend):
    async def scenario():
        message = FakeMessage()
        await main.process_callback(query(message, "help:17:4"))
        await main.process_callback(query(message, "help:17:4"))
        saved = [
            call[3]["json"]
            for call in backend.calls
            if call[1] == "/appeals/17/feedback"
        ]
        assert saved[0] == saved[1] and saved[0]["outcome"] == "helped"

    asyncio.run(scenario())


def test_stale_draft_and_file_limits(backend):
    async def scenario():
        message = FakeMessage(text="Достаточное описание проблемы.")
        await main.process_callback(query(message, "new:problem"))
        first = backend.saved[message.from_user.id]["submission_id"]
        await main.process_callback(query(message, "new:idea"))
        await main.incoming(message)
        with pytest.raises(main.BackendError):
            await main.process_callback(query(message, "submit:" + first))
        message.text = None
        message.photo = [SimpleNamespace(file_id="large", file_size=11 * 1024 * 1024)]
        await main.incoming(message)
        assert backend.saved[message.from_user.id]["files"] == []
        assert "10 МБ" in message.answers[-1][0]

    asyncio.run(scenario())
    with pytest.raises(main.BackendError):
        main.LimitedBuffer().write(b"x" * (10 * 1024 * 1024 + 1))


def test_unscoped_text_never_becomes_appeal_or_reply(backend):
    message = FakeMessage(text="Давайте обед за счёт компании")
    asyncio.run(main.incoming(message))
    assert not any(
        call[0] == "POST" and call[1].startswith("/appeals") for call in backend.calls
    )
    assert "Сначала выберите действие" in message.answers[-1][0]


def test_ai_questions_require_explicit_apply_and_preserve_original(
    backend, monkeypatch
):
    original_call = backend.call

    async def with_ai(method, path, telegram_id=None, **kwargs):
        if path == "/ai/status":
            return {"mode": "demo", "available": True}
        if path == "/ai/appeal":
            return {
                "mode": "demo",
                "suggestion": {
                    "title": "Маркировка полок склада",
                    "description": "Предлагаю маркировать полки склада по типу коробок.",
                    "category": "warehouse",
                    "questions": []
                    if kwargs["json"]["answers"]
                    else ["Где?", "Какой результат?"],
                },
            }
        return await original_call(method, path, telegram_id, **kwargs)

    monkeypatch.setattr(backend, "call", with_ai)

    async def scenario():
        message = FakeMessage(text="На складе не хватает маркировки полок.")
        await main.process_callback(query(message, "new:idea"))
        await main.incoming(message)
        source = message.text
        await main.process_callback(query(message, "ai"))
        draft = backend.saved[message.from_user.id]
        assert draft["description"] == source
        await main.process_callback(query(message, "ai-answers:" + draft["ai_id"]))
        message.text = "На второй полке"
        await main.incoming(message)
        message.text = "Не путать коробки"
        await main.incoming(message)
        draft = backend.saved[message.from_user.id]
        assert draft["description"] == source and len(draft["ai_answers"]) == 2
        await main.process_callback(query(message, "ai-apply:" + draft["ai_id"]))
        assert backend.saved[message.from_user.id]["original_description"] == source
        await main.process_callback(query(message, "submit:" + draft["submission_id"]))
        submit = next(
            call for call in backend.calls if call[:2] == ("POST", "/appeals")
        )
        fields = {name: value[1] for name, value in submit[3]["files"]}
        assert (
            fields["original_description"] == source
            and fields["category"] == "warehouse"
        )

    asyncio.run(scenario())


def test_openrouter_requires_consent_for_current_provider(backend, monkeypatch):
    original_call = backend.call
    calls = []

    async def with_router(method, path, telegram_id=None, **kwargs):
        calls.append(path)
        if path == "/ai/status":
            return {"mode": "openrouter", "available": True}
        if path == "/ai/appeal":
            return {
                "mode": "openrouter",
                "suggestion": {
                    "title": "Маркировка полок склада",
                    "description": "Предлагаю маркировать полки склада.",
                    "category": "warehouse",
                    "questions": [],
                },
            }
        return await original_call(method, path, telegram_id, **kwargs)

    monkeypatch.setattr(backend, "call", with_router)

    async def scenario():
        message = FakeMessage(text="На складе не хватает маркировки полок.")
        await main.process_callback(query(message, "new:idea"))
        await main.incoming(message)
        await main.process_callback(query(message, "ai"))
        assert "/ai/appeal" not in calls and "OpenRouter" in message.answers[-1][0]
        await main.process_callback(query(message, "ai-consent:openai"))
        assert "/ai/appeal" not in calls
        await main.process_callback(query(message, "ai-consent:openrouter"))
        assert calls.count("/ai/appeal") == 1

    asyncio.run(scenario())


def test_similar_appeal_offers_join_instead_of_duplicate(backend):
    similar = [
        {
            "id": 6,
            "number": "MT-000006",
            "title": "Сканер теряет соединение во время комплектации",
            "status": "in_progress",
            "relation": "other",
            "can_join": True,
        }
    ]
    original = backend.call

    async def call(method, path, telegram_id=None, **kwargs):
        if path == "/similar":
            backend.calls.append((method, path, telegram_id, deepcopy(kwargs)))
            return similar
        if path == "/appeals/6/support":
            backend.calls.append((method, path, telegram_id, deepcopy(kwargs)))
            return {"number": "MT-000006", "title": similar[0]["title"]}
        return await original(method, path, telegram_id, **kwargs)

    backend.call = call

    async def scenario():
        message = FakeMessage(text="Сканер отключается от wifi во время сборки заказа.")
        await main.process_callback(query(message, "new:problem"))
        await main.incoming(message)
        text, options = message.answers[-1]
        assert "Похоже, об этом уже сообщали" in text and "MT-000006" in text
        buttons = [b.callback_data for row in options["reply_markup"].inline_keyboard for b in row]
        assert buttons[0] == "join:6"
        await main.process_callback(query(message, "join:6"))
        assert backend.saved[message.from_user.id] == {}
        assert "присоединились к MT-000006" in message.answers[-1][0]
        assert not any(call[:2] == ("POST", "/appeals") for call in backend.calls)

    asyncio.run(scenario())


def test_similar_search_failure_does_not_block_preview(backend):
    original = backend.call

    async def call(method, path, telegram_id=None, **kwargs):
        if path == "/similar":
            raise main.BackendError("Сервис недоступен")
        return await original(method, path, telegram_id, **kwargs)

    backend.call = call

    async def scenario():
        message = FakeMessage(text="На складе не хватает маркировки полок.")
        await main.process_callback(query(message, "new:problem"))
        await main.incoming(message)
        assert "Проверьте обращение" in message.answers[-1][0]
        assert "Похоже" not in message.answers[-1][0]

    asyncio.run(scenario())


def test_voice_needs_consent_then_becomes_description(backend):
    original = backend.call

    async def call(method, path, telegram_id=None, **kwargs):
        if path == "/ai/status":
            return {"available": True, "mode": "openrouter", "voice": True}
        if path == "/ai/transcribe":
            backend.calls.append((method, path, telegram_id, deepcopy(kwargs)))
            return {"text": "Сканер отключается от wifi во время сборки заказа"}
        if path == "/similar":
            return []
        return await original(method, path, telegram_id, **kwargs)

    backend.call = call

    async def scenario():
        message = FakeMessage()
        await main.process_callback(query(message, "new:problem"))
        message.voice = SimpleNamespace(file_id="voice-id", file_size=2048, mime_type="audio/ogg")
        await main.incoming(message)
        text, options = message.answers[-1]
        assert "OpenRouter" in text
        # Nothing leaves the bot before the explicit tap.
        assert not any(call[1] == "/ai/transcribe" for call in backend.calls)
        await main.process_callback(query(message, "voice-ok"))
        draft = backend.saved[message.from_user.id]
        assert draft["description"].startswith("Сканер отключается")
        assert "pending_voice" not in draft and draft["voice"] is True
        assert "Проверьте обращение" in message.answers[-1][0]
        sent = next(call for call in backend.calls if call[1] == "/ai/transcribe")
        assert sent[3]["files"]["file"][1] == b"file-bytes"

    asyncio.run(scenario())


def test_voice_reply_is_sent_only_after_confirmation(backend):
    original = backend.call

    async def call(method, path, telegram_id=None, **kwargs):
        if path == "/ai/status":
            return {"available": True, "mode": "openrouter", "voice": True}
        if path == "/ai/transcribe":
            return {"text": "Путают на второй полке слева"}
        return await original(method, path, telegram_id, **kwargs)

    backend.call = call

    async def scenario():
        message = FakeMessage()
        await main.process_callback(query(message, "reply:17"))
        message.voice = SimpleNamespace(file_id="voice-id", file_size=2048, mime_type="audio/ogg")
        await main.incoming(message)
        await main.process_callback(query(message, "voice-ok"))
        assert not any(call[1] == "/appeals/17/messages" for call in backend.calls)
        await main.process_callback(query(message, "voice-send"))
        sent = next(call for call in backend.calls if call[1] == "/appeals/17/messages")
        assert sent[3]["json"]["body"] == "Путают на второй полке слева"
        assert backend.saved[message.from_user.id] == {}

    asyncio.run(scenario())


def test_voice_without_transcription_asks_for_text(backend):
    async def scenario():
        message = FakeMessage()
        await main.process_callback(query(message, "new:problem"))
        message.voice = SimpleNamespace(file_id="voice-id", file_size=2048, mime_type="audio/ogg")
        await main.incoming(message)
        assert "текстом" in message.answers[-1][0]

    asyncio.run(scenario())
