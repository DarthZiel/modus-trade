from datetime import datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func, or_
from sqlalchemy.dialects.postgresql import insert
from sqlmodel import Session, select

from app.models import (
    Appeal,
    AppealSupporter,
    Experiment,
    Notification,
    User,
    utcnow,
)
from app.security import CurrentUser, Db

router = APIRouter(prefix="/notifications", tags=["Notifications"])


def emit(
    db: Session,
    appeal: Appeal,
    kind: str,
    title: str,
    key: str,
    recipients: set[UUID],
    actor: UUID | None = None,
):
    for user_id in recipients - {actor}:
        user = db.get(User, user_id)
        if not user or not user.is_active:
            continue
        db.execute(
            insert(Notification)
            .values(
                user_id=user_id,
                appeal_id=appeal.id,
                kind=kind,
                title=title,
                dedupe_key=key,
                created_at=utcnow(),
            )
            .on_conflict_do_nothing(index_elements=["user_id", "dedupe_key"])
        )


def coordinators(db: Session) -> set[UUID]:
    return {
        u.id
        for u in db.exec(select(User).where(User.is_active)).all()
        if "coordinator" in u.roles
    }


def participants(db: Session, appeal: Appeal) -> set[UUID]:
    responsible = db.get(User, appeal.responsible_id) if appeal.responsible_id else None
    managers = (
        {responsible.id}
        if responsible and responsible.is_active and "responsible" in responsible.roles
        else coordinators(db)
    )
    return {appeal.author_id} | managers


# Colleagues who joined an appeal follow its official progress, not the private thread.
SUPPORTER_KINDS = {
    "assignment",
    "start",
    "resolve",
    "reject",
    "helped",
    "reopen",
    "experiment_started",
    "experiment_finished",
}


def announce(
    db: Session, appeal: Appeal, kind: str, title: str, actor: UUID | None = None
):
    recipients = participants(db, appeal)
    if kind in SUPPORTER_KINDS:
        recipients |= set(
            db.exec(
                select(AppealSupporter.user_id).where(
                    AppealSupporter.appeal_id == appeal.id
                )
            ).all()
        )
    emit(
        db,
        appeal,
        kind,
        title,
        f"{appeal.id}:{appeal.assignment_version}:{kind}",
        recipients,
        actor,
    )


def scan_reminders(db: Session, now: datetime | None = None) -> None:
    now = now or utcnow()
    # Row locks serialize scans with review/assignment changes and other workers.
    appeals = db.exec(
        select(Appeal)
        .where(
            or_(
                (Appeal.next_response_at < now)
                & Appeal.status.in_(
                    ["received", "reviewing", "in_progress", "needs_info"]
                ),
                (Appeal.status == "awaiting_confirmation")
                & (Appeal.decided_at <= now - timedelta(days=3)),
            )
        )
        .with_for_update(skip_locked=True)
    ).all()
    for appeal in appeals:
        if appeal.status == "awaiting_confirmation":
            emit(
                db,
                appeal,
                "confirmation_reminder",
                "Подтвердите результат рассмотрения",
                f"confirmation:{appeal.id}:{appeal.decided_at.isoformat()}",
                {appeal.author_id},
            )
        else:
            recipients = coordinators(db)
            responsible = (
                db.get(User, appeal.responsible_id) if appeal.responsible_id else None
            )
            if (
                responsible
                and responsible.is_active
                and "responsible" in responsible.roles
            ):
                recipients.add(responsible.id)
            emit(
                db,
                appeal,
                "overdue",
                "Срок ответа истёк",
                f"overdue:{appeal.id}:{appeal.responsible_id}:{appeal.next_response_at.isoformat()}",
                recipients,
            )
    for experiment in db.exec(
        select(Experiment)
        .where(Experiment.status == "active", Experiment.ends_at < now)
        .with_for_update(skip_locked=True)
    ).all():
        appeal = db.get(Appeal, experiment.appeal_id)
        recipients = coordinators(db)
        responsible = (
            db.get(User, appeal.responsible_id) if appeal.responsible_id else None
        )
        if responsible and responsible.is_active and "responsible" in responsible.roles:
            recipients.add(responsible.id)
        emit(
            db,
            appeal,
            "experiment_overdue",
            "Завершился срок эксперимента",
            f"experiment:{experiment.id}:{experiment.ends_at.isoformat()}:{appeal.responsible_id}",
            recipients,
        )
    db.commit()


def visible(user: User):
    access = Appeal.author_id == user.id
    if "coordinator" in user.roles:
        access = True
    elif "responsible" in user.roles:
        access = or_(access, Appeal.responsible_id == user.id)
    if access is not True:
        supported = select(AppealSupporter.appeal_id).where(
            AppealSupporter.user_id == user.id
        )
        access = or_(
            access,
            Appeal.id.in_(supported) & Notification.kind.in_(SUPPORTER_KINDS),
        )
    return (
        select(Notification).join(Appeal).where(Notification.user_id == user.id, access)
    )


def link_prefix(appeal: Appeal, user: User) -> str:
    """Authors and supporters open the employee card; staff open the queue card."""
    staff = "coordinator" in user.roles or (
        "responsible" in user.roles and appeal.responsible_id == user.id
    )
    return "queue" if staff and appeal.author_id != user.id else "appeals"


@router.get("")
def listing(user: CurrentUser, db: Db, page: int = Query(1, ge=1)):
    query = visible(user)
    unread = db.exec(
        select(func.count()).select_from(
            query.where(Notification.read_at.is_(None)).subquery()
        )
    ).one()
    total = db.exec(select(func.count()).select_from(query.subquery())).one()
    rows = db.exec(
        query.order_by(Notification.created_at.desc(), Notification.id.desc())
        .offset((page - 1) * 20)
        .limit(20)
    ).all()
    items = []
    for item in rows:
        appeal = db.get(Appeal, item.appeal_id)
        prefix = link_prefix(appeal, user)
        items.append(
            {
                "id": item.id,
                "title": item.title,
                "kind": item.kind,
                "number": f"MT-{appeal.id:06}",
                "appeal_title": appeal.title,
                "url": f"/{prefix}/{appeal.id}",
                "created_at": item.created_at,
                "read_at": item.read_at,
            }
        )
    return {"items": items, "unread": unread, "total": total, "page": page}


@router.post("/read-all", status_code=204)
def read_all(user: CurrentUser, db: Db):
    for item in db.exec(visible(user).where(Notification.read_at.is_(None))).all():
        item.read_at = utcnow()
        db.add(item)
    db.commit()


@router.post("/{notification_id}/read", status_code=204)
def read_one(notification_id: UUID, user: CurrentUser, db: Db):
    item = db.exec(visible(user).where(Notification.id == notification_id)).first()
    if not item:
        raise HTTPException(404, "Уведомление не найдено")
    if item.read_at is None:
        item.read_at = utcnow()
        db.add(item)
        db.commit()
