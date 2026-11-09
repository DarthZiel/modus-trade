from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlmodel import select

from app.appeal_schemas import (
    AppealDetail,
    AppealKind,
    AppealPage,
    AppealStatus,
    AssignmentInput,
    ResponsiblePublic,
)
from app.appeals import detail, summary
from app.models import (
    Appeal,
    AppealAttachment,
    AppealEvent,
    Company,
    Department,
    Experiment,
    User,
    utcnow,
)
from app.notifications import announce
from app.security import Coordinator, CurrentUser, Db

router = APIRouter(prefix="/work", tags=["Work queue"])


def work_user(user: CurrentUser) -> User:
    if not {"coordinator", "responsible"}.intersection(user.roles):
        raise HTTPException(403, "Доступно координатору и ответственному")
    return user


WorkUser = Annotated[User, Depends(work_user)]
QueueFilter = Literal["all", "mine", "unassigned", "overdue", "awaiting_confirmation"]


@router.get("/responsibles")
def responsible_options(actor: Coordinator, db: Db) -> list[ResponsiblePublic]:
    users = db.exec(
        select(User).where(User.is_active == True).order_by(User.name, User.id)
    ).all()
    return [
        ResponsiblePublic(
            id=user.id,
            name=user.name,
            company=db.get(Company, user.company_id).name,
            department=db.get(Department, user.department_id).name,
        )
        for user in users
        if "responsible" in user.roles
    ]


@router.get("/appeals")
def queue(
    actor: WorkUser,
    db: Db,
    filter: QueueFilter = "all",
    status: AppealStatus | None = None,
    kind: AppealKind | None = None,
    company_id: UUID | None = None,
    department_id: UUID | None = None,
    responsible_id: UUID | None = None,
    q: Annotated[str, Query(max_length=200)] = "",
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=50)] = 20,
) -> AppealPage:
    conditions = []
    if "coordinator" not in actor.roles or filter == "mine":
        conditions.append(Appeal.responsible_id == actor.id)
    if filter == "unassigned":
        conditions.append(Appeal.responsible_id == None)
    elif filter == "overdue":
        conditions.extend(
            [
                Appeal.next_response_at < utcnow(),
                Appeal.status.notin_(["closed", "rejected"]),
            ]
        )
    elif filter == "awaiting_confirmation":
        conditions.append(Appeal.status == "awaiting_confirmation")
    for column, value in (
        (Appeal.status, status),
        (Appeal.kind, kind),
        (Appeal.company_id, company_id),
        (Appeal.department_id, department_id),
        (Appeal.responsible_id, responsible_id),
    ):
        if value is not None:
            conditions.append(column == value)
    query = q.strip()
    if query:
        escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        pattern = f"%{escaped}%"
        match = Appeal.title.ilike(pattern, escape="\\") | Appeal.description.ilike(
            pattern, escape="\\"
        )
        match = match | Appeal.author_id.in_(
            select(User.id).where(User.name.ilike(pattern, escape="\\"))
        )
        number = query.upper().removeprefix("MT-")
        if (
            number.isascii()
            and number.isdigit()
            and len(number) <= 10
            and int(number) <= 2147483647
        ):
            match = match | (Appeal.id == int(number))
        conditions.append(match)
    total = db.exec(select(func.count()).select_from(Appeal).where(*conditions)).one()
    counts = (
        select(AppealAttachment.appeal_id, func.count().label("count"))
        .group_by(AppealAttachment.appeal_id)
        .subquery()
    )
    rows = db.exec(
        select(Appeal, func.coalesce(counts.c.count, 0))
        .outerjoin(counts, counts.c.appeal_id == Appeal.id)
        .where(*conditions)
        .order_by(Appeal.created_at.desc(), Appeal.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return AppealPage(
        items=[summary(appeal, db, count) for appeal, count in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.patch("/appeals/{appeal_id}/assignment")
def assign(
    appeal_id: int, data: AssignmentInput, actor: Coordinator, db: Db
) -> AppealDetail:
    appeal = db.exec(
        select(Appeal).where(Appeal.id == appeal_id).with_for_update()
    ).first()
    if not appeal:
        raise HTTPException(404, "Обращение не найдено")
    if appeal.status in {"closed", "rejected"}:
        raise HTTPException(409, "Нельзя менять назначение завершённого обращения")
    if appeal.assignment_version != data.expected_version:
        raise HTTPException(
            409, "Назначение уже изменено другим координатором. Обновите карточку."
        )
    target = db.get(User, data.responsible_id)
    if not target or not target.is_active or "responsible" not in target.roles:
        raise HTTPException(422, "Выберите активного сотрудника с ролью ответственного")
    if data.next_response_at <= utcnow():
        raise HTTPException(422, "Дата следующего ответа должна быть в будущем")
    if (
        appeal.responsible_id == target.id
        and appeal.next_response_at == data.next_response_at
    ):
        return detail(appeal, db)
    if appeal.responsible_id and not data.reason:
        raise HTTPException(422, "Укажите причину переназначения или изменения срока")
    previous = db.get(User, appeal.responsible_id) if appeal.responsible_id else None
    text = (
        f"Ответственный: {target.name}."
        if not previous
        else f"Ответственный: {previous.name} → {target.name}."
    )
    text += f" Следующий ответ до {data.next_response_at.isoformat()}."
    if data.reason:
        text += f" Причина: {data.reason}"
    appeal.responsible_id = target.id
    appeal.next_response_at = data.next_response_at
    # Shared revision also guards against stale review and decision forms.
    appeal.assignment_version += 1
    if appeal.status == "received":
        appeal.status = "reviewing"
    db.add(appeal)
    for experiment in db.exec(
        select(Experiment).where(
            Experiment.appeal_id == appeal.id, Experiment.status == "active"
        )
    ).all():
        if experiment.responsible_id != appeal.responsible_id:
            experiment.responsible_id = appeal.responsible_id
            experiment.version += 1
            db.add(experiment)
    db.add(AppealEvent(appeal_id=appeal.id, actor_id=actor.id, text=text))
    announce(db, appeal, "assignment", "Назначение и срок ответа обновлены", actor.id)
    db.commit()
    return detail(appeal, db)


@router.get("/overview")
def overview(actor: WorkUser, db: Db) -> dict[str, int]:
    conditions = (
        [] if "coordinator" in actor.roles else [Appeal.responsible_id == actor.id]
    )
    appeals = db.exec(select(Appeal).where(*conditions)).all()
    ids = [item.id for item in appeals]
    active_experiments = (
        db.exec(
            select(func.count())
            .select_from(Experiment)
            .where(Experiment.appeal_id.in_(ids), Experiment.status == "active")
        ).one()
        if ids
        else 0
    )
    return {
        "unassigned": sum(
            item.responsible_id is None and item.status not in {"closed", "rejected"}
            for item in appeals
        ),
        "overdue": sum(
            item.next_response_at is not None
            and item.next_response_at < utcnow()
            and item.status not in {"closed", "rejected"}
            for item in appeals
        ),
        "active_experiments": active_experiments,
        "awaiting_confirmation": sum(
            item.status == "awaiting_confirmation" for item in appeals
        ),
        "confirmed": sum(item.status == "closed" for item in appeals),
    }
