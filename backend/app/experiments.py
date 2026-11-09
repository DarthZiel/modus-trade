from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    FiniteFloat,
    model_validator,
)
from sqlalchemy import text
from sqlmodel import select

from app.appeals import accessible
from app.models import Appeal, AppealEvent, Experiment, User, utcnow
from app.notifications import announce
from app.security import CurrentUser, Db

router = APIRouter(prefix="/appeals", tags=["Experiments"])


class PlanInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    client_id: UUID
    expected_version: int = Field(ge=0)
    hypothesis: str = Field(min_length=5, max_length=2000)
    change: str = Field(min_length=5, max_length=3000)
    success_criterion: str = Field(min_length=5, max_length=2000)
    starts_at: AwareDatetime
    ends_at: AwareDatetime
    planned_cost: str = Field(default="", max_length=1000)
    baseline: str = Field(default="", max_length=2000)
    metric: str = Field(default="", max_length=160)
    unit: str = Field(default="", max_length=80)
    before_value: FiniteFloat | None = None

    @model_validator(mode="after")
    def valid_measurement(self):
        if self.ends_at <= self.starts_at:
            raise ValueError("Завершение должно быть позже начала")
        if self.before_value is not None and (not self.metric or not self.unit):
            raise ValueError("Для измерения укажите показатель и единицу")
        return self


class FinishInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    expected_version: int = Field(ge=0)
    actions: str = Field(min_length=5, max_length=3000)
    actual_cost: str = Field(default="", max_length=1000)
    observations: str = Field(min_length=5, max_length=3000)
    after_value: FiniteFloat | None = None
    outcome: Literal["expand", "iterate", "stop"]


class ExperimentPublic(BaseModel):
    id: UUID
    appeal_id: int
    responsible: str
    hypothesis: str
    change: str
    success_criterion: str
    starts_at: datetime
    ends_at: datetime
    planned_cost: str
    baseline: str
    metric: str
    unit: str
    before_value: float | None
    after_value: float | None
    status: str
    version: int
    actions: str
    actual_cost: str
    observations: str
    author_comment: str
    outcome: str | None
    finished_at: datetime | None
    quantitative_evidence: bool
    delta: float | None
    is_overdue: bool


def public(item: Experiment, db) -> ExperimentPublic:
    measured = (
        item.before_value is not None
        and item.after_value is not None
        and bool(item.metric and item.unit)
    )
    return ExperimentPublic(
        **item.model_dump(exclude={"responsible_id"}),
        responsible=db.get(User, item.responsible_id).name,
        quantitative_evidence=measured,
        delta=item.after_value - item.before_value if measured else None,
        is_overdue=item.status == "active" and item.ends_at < utcnow(),
    )


def manager(appeal, user):
    if not (
        "coordinator" in user.roles
        or ("responsible" in user.roles and appeal.responsible_id == user.id)
    ):
        raise HTTPException(403, "Эксперимент ведёт ответственный или координатор")


@router.get("/{appeal_id}/experiments")
def listing(appeal_id: int, user: CurrentUser, db: Db) -> list[ExperimentPublic]:
    accessible(db.get(Appeal, appeal_id), user)
    return [
        public(item, db)
        for item in db.exec(
            select(Experiment)
            .where(Experiment.appeal_id == appeal_id)
            .order_by(Experiment.created_at.desc())
        ).all()
    ]


@router.post("/{appeal_id}/experiments", status_code=201)
def create(
    appeal_id: int, data: PlanInput, user: CurrentUser, db: Db
) -> ExperimentPublic:
    db.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:key))"),
        {"key": f"experiment:{user.id}:{data.client_id}"},
    )
    appeal = accessible(
        db.exec(select(Appeal).where(Appeal.id == appeal_id).with_for_update()).first(),
        user,
    )
    manager(appeal, user)
    previous = db.exec(
        select(Experiment).where(
            Experiment.created_by == user.id, Experiment.client_id == data.client_id
        )
    ).first()
    values = data.model_dump(exclude={"client_id", "expected_version"})
    if previous:
        if previous.appeal_id != appeal_id or any(
            getattr(previous, key) != value for key, value in values.items()
        ):
            raise HTTPException(409, "С этим ключом уже создан другой план")
        return public(previous, db)
    if appeal.assignment_version != data.expected_version:
        raise HTTPException(409, "Обращение изменилось. Обновите карточку.")
    if appeal.status not in {"reviewing", "in_progress"}:
        raise HTTPException(
            409, "Эксперимент можно запустить при рассмотрении или выполнении"
        )
    responsible = db.get(User, appeal.responsible_id) if appeal.responsible_id else None
    if (
        not responsible
        or not responsible.is_active
        or "responsible" not in responsible.roles
    ):
        raise HTTPException(
            422, "Сначала назначьте доступного ответственного обращению"
        )
    if data.ends_at <= utcnow():
        raise HTTPException(422, "Срок завершения должен быть в будущем")
    if db.exec(
        select(Experiment).where(
            Experiment.appeal_id == appeal_id, Experiment.status == "active"
        )
    ).first():
        raise HTTPException(409, "В обращении уже есть активный эксперимент")
    item = Experiment(
        **values,
        appeal_id=appeal_id,
        created_by=user.id,
        client_id=data.client_id,
        responsible_id=responsible.id,
    )
    db.add(item)
    appeal.status = "in_progress"
    appeal.assignment_version += 1
    db.add(appeal)
    db.add(
        AppealEvent(
            appeal_id=appeal_id,
            actor_id=user.id,
            text="Запущен эксперимент: " + data.hypothesis,
        )
    )
    announce(
        db,
        appeal,
        "experiment_started",
        "Началась проверка идеи экспериментом",
        user.id,
    )
    db.commit()
    return public(item, db)


@router.post("/{appeal_id}/experiments/{experiment_id}/finish")
def finish(
    appeal_id: int, experiment_id: UUID, data: FinishInput, user: CurrentUser, db: Db
) -> ExperimentPublic:
    appeal = accessible(
        db.exec(select(Appeal).where(Appeal.id == appeal_id).with_for_update()).first(),
        user,
    )
    manager(appeal, user)
    item = db.get(Experiment, experiment_id)
    if not item or item.appeal_id != appeal_id:
        raise HTTPException(404, "Эксперимент не найден")
    values = data.model_dump(exclude={"expected_version"})
    if item.status == "completed":
        if all(getattr(item, key) == value for key, value in values.items()):
            return public(item, db)
        raise HTTPException(409, "Результат эксперимента уже зафиксирован")
    if item.version != data.expected_version:
        raise HTTPException(409, "Эксперимент изменился. Обновите карточку.")
    if data.after_value is not None and (not item.metric or not item.unit):
        raise HTTPException(422, "В плане не указан показатель и единица измерения")
    for key, value in values.items():
        setattr(item, key, value)
    item.status = "completed"
    item.finished_at = utcnow()
    item.version += 1
    db.add(item)
    appeal.assignment_version += 1
    db.add(appeal)
    db.add(
        AppealEvent(
            appeal_id=appeal_id,
            actor_id=user.id,
            text="Эксперимент завершён. Итог: "
            + {
                "expand": "внедрить шире",
                "iterate": "доработать",
                "stop": "прекратить",
            }[data.outcome],
        )
    )
    announce(db, appeal, "experiment_finished", "Результат эксперимента готов", user.id)
    db.commit()
    return public(item, db)


class AuthorComment(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    comment: str = Field(min_length=1, max_length=2000)
    expected_version: int = Field(ge=0)


@router.post("/{appeal_id}/experiments/{experiment_id}/comment")
def comment(
    appeal_id: int, experiment_id: UUID, data: AuthorComment, user: CurrentUser, db: Db
) -> ExperimentPublic:
    appeal = accessible(
        db.exec(select(Appeal).where(Appeal.id == appeal_id).with_for_update()).first(),
        user,
    )
    if appeal.author_id != user.id:
        raise HTTPException(403, "Комментарий оставляет автор обращения")
    item = db.get(Experiment, experiment_id)
    if not item or item.appeal_id != appeal_id or item.status != "completed":
        raise HTTPException(409, "Сначала завершите эксперимент")
    if item.author_comment == data.comment:
        return public(item, db)
    if item.version != data.expected_version:
        raise HTTPException(409, "Эксперимент изменился. Обновите карточку.")
    if item.author_comment:
        raise HTTPException(
            409, "Комментарий уже сохранён; дополнения отправьте в переписку"
        )
    item.author_comment = data.comment.strip()
    if not item.author_comment:
        raise HTTPException(422, "Напишите комментарий")
    item.version += 1
    db.add(item)
    appeal.assignment_version += 1
    db.add(appeal)
    db.add(
        AppealEvent(
            appeal_id=appeal_id,
            actor_id=user.id,
            text="Автор прокомментировал эксперимент: " + item.author_comment,
        )
    )
    announce(db, appeal, "experiment_comment", "Автор оценил эксперимент", user.id)
    db.commit()
    return public(item, db)
