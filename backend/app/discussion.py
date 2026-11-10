from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query, Response
from sqlmodel import select

from app.appeal_schemas import (
    AppealDetail,
    MessageInput,
    MessagePage,
    MessagePublic,
    MessageSent,
    ReviewInput,
)
from app.appeals import accessible, detail
from app.models import Appeal, AppealEvent, AppealMessage, Experiment, User, utcnow
from app.notifications import announce
from app.security import CurrentUser, Db

router = APIRouter(prefix="/appeals", tags=["Discussion and review"])


def message_public(message: AppealMessage, appeal: Appeal, db) -> MessagePublic:
    return MessagePublic(
        id=message.id,
        sender_id=message.sender_id,
        sender=db.get(User, message.sender_id).name,
        is_author=message.sender_id == appeal.author_id,
        body=message.body,
        kind=message.kind,
        created_at=message.created_at,
    )


@router.get("/{appeal_id}/messages")
def messages(
    appeal_id: int,
    user: CurrentUser,
    db: Db,
    before_id: Annotated[int | None, Query(ge=1)] = None,
) -> MessagePage:
    appeal = accessible(db.get(Appeal, appeal_id), user)
    query = select(AppealMessage).where(AppealMessage.appeal_id == appeal_id)
    if before_id is not None:
        query = query.where(AppealMessage.id < before_id)
    rows = db.exec(query.order_by(AppealMessage.id.desc()).limit(51)).all()
    return MessagePage(
        items=[message_public(item, appeal, db) for item in reversed(rows[:50])],
        has_more=len(rows) > 50,
    )


@router.post("/{appeal_id}/messages", status_code=201)
def send_message(
    appeal_id: int, data: MessageInput, user: CurrentUser, db: Db, response: Response
) -> MessageSent:
    appeal = accessible(
        db.exec(select(Appeal).where(Appeal.id == appeal_id).with_for_update()).first(),
        user,
    )
    if not (
        appeal.author_id == user.id
        or "coordinator" in user.roles
        or ("responsible" in user.roles and appeal.responsible_id == user.id)
    ):
        raise HTTPException(
            403, "Директор просматривает чужие обращения без изменения переписки"
        )
    previous = db.exec(
        select(AppealMessage).where(
            AppealMessage.appeal_id == appeal_id,
            AppealMessage.sender_id == user.id,
            AppealMessage.client_id == data.client_id,
        )
    ).first()
    if previous:
        if previous.body != data.body:
            raise HTTPException(
                409,
                "С этим ключом уже отправлено другое сообщение. Обновите переписку.",
            )
        response.status_code = 200
        return MessageSent(
            message=message_public(previous, appeal, db), appeal=detail(appeal, db)
        )
    message = AppealMessage(
        appeal_id=appeal_id, sender_id=user.id, client_id=data.client_id, body=data.body
    )
    db.add(message)
    if user.id != appeal.author_id and appeal.first_response_at is None:
        appeal.first_response_at = utcnow()
    if appeal.status == "needs_info" and user.id == appeal.author_id:
        appeal.status = appeal.resume_status or "reviewing"
        appeal.resume_status = None
        db.add(
            AppealEvent(
                appeal_id=appeal_id,
                actor_id=user.id,
                text="Автор ответил на запрос уточнения. Рассмотрение продолжено.",
            )
        )
    appeal.assignment_version += 1
    db.add(appeal)
    announce(db, appeal, "message", "Новое сообщение по обращению", user.id)
    db.commit()
    return MessageSent(
        message=message_public(message, appeal, db), appeal=detail(appeal, db)
    )


@router.post("/{appeal_id}/review")
def review(
    appeal_id: int, data: ReviewInput, user: CurrentUser, db: Db
) -> AppealDetail:
    appeal = accessible(
        db.exec(select(Appeal).where(Appeal.id == appeal_id).with_for_update()).first(),
        user,
    )
    if not (
        "coordinator" in user.roles
        or ("responsible" in user.roles and appeal.responsible_id == user.id)
    ):
        raise HTTPException(
            403, "Рассматривать обращение может ответственный или координатор"
        )
    if data.expected_version != appeal.assignment_version:
        raise HTTPException(
            409, "Обращение изменилось. Обновите карточку перед сохранением решения."
        )
    allowed = {
        "start": {"reviewing"},
        "request_info": {"reviewing", "in_progress"},
        "resolve": {"reviewing", "in_progress"},
        "reject": {"reviewing", "in_progress"},
    }
    if appeal.status not in allowed[data.action]:
        raise HTTPException(409, "Это действие недоступно в текущем статусе обращения")
    if data.action != "start" and not data.explanation:
        raise HTTPException(
            422, "Укажите вопрос, результат выполнения или причину отклонения"
        )
    if (
        data.action in {"resolve", "reject"}
        and db.exec(
            select(Experiment).where(
                Experiment.appeal_id == appeal_id, Experiment.status == "active"
            )
        ).first()
    ):
        raise HTTPException(
            409, "Сначала завершите активный эксперимент и зафиксируйте его результат"
        )
    if data.action == "start":
        appeal.status = "in_progress"
        event = "Обращение принято в работу."
    elif data.action == "request_info":
        appeal.resume_status = appeal.status
        appeal.status = "needs_info"
        db.add(
            AppealMessage(
                appeal_id=appeal_id,
                sender_id=user.id,
                client_id=uuid4(),
                body=data.explanation,
                kind="question",
            )
        )
        event = "Запрошено уточнение у автора."
    elif data.action == "resolve":
        appeal.status = "awaiting_confirmation"
        appeal.next_response_at = None
        appeal.decision = "Выполнено"
        appeal.result = data.explanation
        appeal.decided_at = utcnow()
        event = (
            "Результат выполнения зафиксирован. Ожидается подтверждение автора.\n"
            + data.explanation
        )
    else:
        appeal.status = "rejected"
        appeal.next_response_at = None
        appeal.decision = "Отклонено"
        appeal.result = data.explanation
        appeal.decided_at = utcnow()
        event = "Обращение отклонено. Причина:\n" + data.explanation
    if (
        data.action in {"request_info", "resolve", "reject"}
        and user.id != appeal.author_id
        and appeal.first_response_at is None
    ):
        appeal.first_response_at = utcnow()
    appeal.assignment_version += 1
    db.add(appeal)
    db.add(AppealEvent(appeal_id=appeal_id, actor_id=user.id, text=event))
    announce(
        db,
        appeal,
        data.action,
        {
            "start": "Обращение принято в работу",
            "request_info": "Нужно уточнение от автора",
            "resolve": "Результат готов — подтвердите решение",
            "reject": "Обращение отклонено",
        }[data.action],
        user.id,
    )
    db.commit()
    return detail(appeal, db)
