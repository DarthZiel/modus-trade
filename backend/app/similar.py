"""Similar appeals while typing, and joining an existing appeal instead of a duplicate.

Privacy: employees never see other people's appeal text, author or messages.
A match from someone else exposes only the number, title, category, status,
responsible and how many colleagues joined. Joining gives a limited card with
the official answer (decision, result, experiment), not the private thread.
"""

from datetime import datetime, timedelta
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, text
from sqlmodel import Session, select

from app.appeal_schemas import AppealKind, AppealStatus, Category
from app.models import (
    Appeal,
    AppealEvent,
    AppealSupporter,
    Department,
    Experiment,
    User,
    utcnow,
)
from app.notifications import emit, participants
from app.security import CurrentUser, Db, limiter

router = APIRouter(tags=["Similar appeals"])

FINAL = {"closed", "rejected"}
# Tuned on the showcase appeals with rephrased queries: every true match scored
# >= 0.19, the best unrelated one 0.16. Titles carry most of the signal; the
# description catches rephrasings ("сканер отключается" vs "теряет соединение").
THRESHOLD = 0.18
RESOLVED_WINDOW = timedelta(days=180)


class SimilarInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    title: str = Field(default="", max_length=160)
    description: str = Field(default="", max_length=10000)
    kind: AppealKind | None = None
    exclude_id: int | None = None


class SimilarAppeal(BaseModel):
    id: int
    number: str
    title: str
    kind: AppealKind
    category: Category
    status: AppealStatus
    responsible: str | None
    supporters: int
    created_at: datetime
    relation: Literal["own", "supported", "other"]
    can_join: bool
    score: float


class SupportInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    comment: str = Field(default="", max_length=1000)


class SupportExperiment(BaseModel):
    hypothesis: str
    change: str
    starts_at: datetime
    ends_at: datetime
    status: str
    outcome: str | None


class SupportView(BaseModel):
    id: int
    number: str
    title: str
    kind: AppealKind
    category: Category
    status: AppealStatus
    responsible: str | None
    next_response_at: datetime | None
    is_overdue: bool
    decision: str | None
    result: str | None
    decided_at: datetime | None
    supporters: int
    joined_at: datetime
    comment: str
    experiment: SupportExperiment | None


def supporter_count(db: Session, appeal_id: int) -> int:
    return db.exec(
        select(func.count())
        .select_from(AppealSupporter)
        .where(AppealSupporter.appeal_id == appeal_id)
    ).one()


def supporter_ids(db: Session, appeal_id: int) -> set:
    return set(
        db.exec(
            select(AppealSupporter.user_id).where(AppealSupporter.appeal_id == appeal_id)
        ).all()
    )


def normalize(value: str) -> str:
    return " ".join(value.lower().replace("ё", "е").split())


def find_similar(db: Session, user: User, data: SimilarInput) -> list[SimilarAppeal]:
    title = normalize(data.title)
    body = normalize(f"{data.title} {data.description}")[:600]
    if len(body) < 12:
        return []
    rows = db.execute(
        text(
            """
            WITH scored AS (
              SELECT a.id,
                similarity(lower(replace(a.title, 'ё', 'е')), :title) AS by_title,
                word_similarity(:title, lower(replace(a.title || ' ' || left(a.description, 1500), 'ё', 'е'))) AS in_text,
                similarity(lower(replace(left(a.title || ' ' || a.description, 600), 'ё', 'е')), :body) AS by_body
              FROM appeals a
              WHERE a.company_id = :company
                AND a.status <> 'rejected'
                AND (a.status <> 'closed' OR a.decided_at > :resolved_after)
                AND (CAST(:exclude AS integer) IS NULL OR a.id <> :exclude)
            )
            SELECT id,
              CASE WHEN :title = '' THEN by_body
                   ELSE 0.5 * by_title + 0.25 * in_text + 0.25 * by_body END AS score
            FROM scored
            ORDER BY score DESC
            LIMIT 5
            """
        ),
        {
            "title": title,
            "body": body,
            "company": user.company_id,
            "resolved_after": utcnow() - RESOLVED_WINDOW,
            "exclude": data.exclude_id,
        },
    ).all()
    result = []
    for appeal_id, score in rows:
        if score < THRESHOLD:
            continue
        appeal = db.get(Appeal, appeal_id)
        supporters = supporter_ids(db, appeal.id)
        relation = (
            "own"
            if appeal.author_id == user.id
            else "supported"
            if user.id in supporters
            else "other"
        )
        responsible = (
            db.get(User, appeal.responsible_id) if appeal.responsible_id else None
        )
        result.append(
            SimilarAppeal(
                id=appeal.id,
                number=f"MT-{appeal.id:06d}",
                title=appeal.title,
                kind=appeal.kind,
                category=appeal.category,
                status=appeal.status,
                responsible=responsible.name if responsible else None,
                supporters=len(supporters),
                created_at=appeal.created_at,
                relation=relation,
                can_join=relation == "other" and appeal.status not in FINAL,
                score=round(float(score), 3),
            )
        )
    return result


@router.post("/similar")
def similar(data: SimilarInput, user: CurrentUser, db: Db) -> list[SimilarAppeal]:
    limiter.check(f"similar:{user.id}", limit=120)
    return find_similar(db, user, data)


def support_view(db: Session, appeal: Appeal, row: AppealSupporter) -> SupportView:
    responsible = db.get(User, appeal.responsible_id) if appeal.responsible_id else None
    experiment = db.exec(
        select(Experiment)
        .where(Experiment.appeal_id == appeal.id)
        .order_by(Experiment.created_at.desc())
    ).first()
    return SupportView(
        id=appeal.id,
        number=f"MT-{appeal.id:06d}",
        title=appeal.title,
        kind=appeal.kind,
        category=appeal.category,
        status=appeal.status,
        responsible=responsible.name if responsible else None,
        next_response_at=appeal.next_response_at,
        is_overdue=bool(
            appeal.next_response_at
            and appeal.next_response_at < utcnow()
            and appeal.status not in FINAL
        ),
        decision=appeal.decision,
        result=appeal.result,
        decided_at=appeal.decided_at,
        supporters=supporter_count(db, appeal.id),
        joined_at=row.created_at,
        comment=row.comment,
        experiment=SupportExperiment(
            hypothesis=experiment.hypothesis,
            change=experiment.change,
            starts_at=experiment.starts_at,
            ends_at=experiment.ends_at,
            status=experiment.status,
            outcome=experiment.outcome,
        )
        if experiment
        else None,
    )


def own_support(db: Session, appeal_id: int, user: User) -> AppealSupporter | None:
    return db.exec(
        select(AppealSupporter).where(
            AppealSupporter.appeal_id == appeal_id, AppealSupporter.user_id == user.id
        )
    ).first()


@router.post("/appeals/{appeal_id}/support")
def join(
    appeal_id: int, data: SupportInput, user: CurrentUser, db: Db
) -> SupportView:
    appeal = db.exec(
        select(Appeal).where(Appeal.id == appeal_id).with_for_update()
    ).first()
    if not appeal or appeal.company_id != user.company_id:
        raise HTTPException(404, "Обращение не найдено")
    if appeal.author_id == user.id:
        raise HTTPException(
            409, "Это ваше обращение. Дополните его сообщением в переписке."
        )
    existing = own_support(db, appeal_id, user)
    if existing:
        return support_view(db, appeal, existing)
    if appeal.status in FINAL:
        raise HTTPException(
            409, "Обращение уже завершено. Если проблема осталась, создайте новое."
        )
    row = AppealSupporter(appeal_id=appeal_id, user_id=user.id, comment=data.comment)
    db.add(row)
    department = db.get(Department, user.department_id)
    event = f"{user.name} ({department.name}) присоединился: у него та же ситуация."
    if data.comment:
        event += "\nКомментарий: " + data.comment
    db.add(AppealEvent(appeal_id=appeal_id, actor_id=user.id, text=event))
    db.flush()
    count = supporter_count(db, appeal_id)
    emit(
        db,
        appeal,
        "support",
        f"К обращению присоединились: {count}",
        f"support:{appeal_id}:{user.id}",
        participants(db, appeal),
        user.id,
    )
    db.commit()
    return support_view(db, appeal, row)


@router.get("/appeals/{appeal_id}/support")
def supported_card(appeal_id: int, user: CurrentUser, db: Db) -> SupportView:
    appeal = db.get(Appeal, appeal_id)
    row = own_support(db, appeal_id, user) if appeal else None
    if not row:
        raise HTTPException(404, "Обращение не найдено")
    return support_view(db, appeal, row)


@router.get("/supports")
def my_supports(user: CurrentUser, db: Db) -> list[SupportView]:
    rows = db.exec(
        select(AppealSupporter)
        .where(AppealSupporter.user_id == user.id)
        .order_by(AppealSupporter.created_at.desc())
        .limit(50)
    ).all()
    return [support_view(db, db.get(Appeal, row.appeal_id), row) for row in rows]
