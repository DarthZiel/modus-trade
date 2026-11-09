from uuid import uuid4

from fastapi import APIRouter, HTTPException
from sqlalchemy import text
from sqlmodel import select

from app.appeal_schemas import AppealDetail, FeedbackInput
from app.appeals import accessible, detail
from app.models import Appeal, AppealEvent, AppealFeedback, AppealMessage, User
from app.notifications import announce
from app.security import CurrentUser, Db

router = APIRouter(prefix="/appeals", tags=["Author feedback"])


@router.post("/{appeal_id}/feedback")
def feedback(
    appeal_id: int, data: FeedbackInput, user: CurrentUser, db: Db
) -> AppealDetail:
    db.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:key))"),
        {"key": f"feedback:{user.id}:{data.client_id}"},
    )
    appeal = accessible(
        db.exec(select(Appeal).where(Appeal.id == appeal_id).with_for_update()).first(),
        user,
    )
    if appeal.author_id != user.id:
        raise HTTPException(
            403, "Подтвердить результат или вернуть обращение может только автор"
        )
    previous = db.exec(
        select(AppealFeedback).where(
            AppealFeedback.author_id == user.id,
            AppealFeedback.client_id == data.client_id,
        )
    ).first()
    if previous:
        if (
            previous.appeal_id != appeal_id
            or previous.outcome != data.outcome
            or previous.comment != data.comment
        ):
            raise HTTPException(
                409, "С этим ключом уже сохранён другой ответ. Обновите карточку."
            )
        return detail(appeal, db)
    if appeal.assignment_version != data.expected_version:
        raise HTTPException(
            409,
            "Обращение изменилось. Обновите карточку перед подтверждением результата.",
        )
    if appeal.status != "awaiting_confirmation" or not appeal.result:
        raise HTTPException(
            409, "Результат этого обращения сейчас не ожидает подтверждения"
        )
    if data.outcome == "reopen" and not data.comment:
        raise HTTPException(422, "Опишите, почему проблема осталась")
    db.add(
        AppealFeedback(
            appeal_id=appeal_id,
            author_id=user.id,
            client_id=data.client_id,
            outcome=data.outcome,
            comment=data.comment,
            result_snapshot=appeal.result,
        )
    )
    if data.outcome == "helped":
        appeal.status = "closed"
        event = "Автор подтвердил результат. Обращение закрыто."
        if data.comment:
            event += "\n" + data.comment
    else:
        responsible = (
            db.get(User, appeal.responsible_id) if appeal.responsible_id else None
        )
        available = (
            responsible and responsible.is_active and "responsible" in responsible.roles
        )
        appeal.status = "in_progress" if available else "received"
        if not available:
            appeal.responsible_id = None
        appeal.decision = None
        appeal.result = None
        appeal.decided_at = None
        appeal.resume_status = None
        appeal.next_response_at = None
        event = (
            "Автор вернул обращение в работу."
            if available
            else "Автор вернул обращение. Требуется назначение нового ответственного."
        )
        event += "\nПричина: " + data.comment
        db.add(
            AppealMessage(
                appeal_id=appeal_id,
                sender_id=user.id,
                client_id=uuid4(),
                body=data.comment,
                kind="feedback_return",
            )
        )
    appeal.assignment_version += 1
    db.add(appeal)
    db.add(AppealEvent(appeal_id=appeal_id, actor_id=user.id, text=event))
    announce(
        db,
        appeal,
        data.outcome,
        "Автор подтвердил результат"
        if data.outcome == "helped"
        else "Автор вернул обращение в работу",
        user.id,
    )
    db.commit()
    return detail(appeal, db)
