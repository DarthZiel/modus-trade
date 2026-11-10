"""Cohort statistics: appeals submitted in a selected local calendar period."""

from collections import Counter
from datetime import UTC, date, datetime, time, timedelta
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from sqlmodel import select

from app.models import Appeal, AppealFeedback, utcnow
from app.security import InsightReader, Db
from app.similarities import RelatedAppeal, TopicPublic, brief, topic_groups

router = APIRouter(prefix="/work", tags=["Statistics"])


class CountItem(BaseModel):
    key: str
    count: int


class TrendItem(BaseModel):
    date: date
    received: int
    confirmed: int


class StatisticAppeal(RelatedAppeal):
    kind: str
    category: str
    company_id: UUID
    department_id: UUID
    first_response_at: datetime | None
    overdue: bool
    confirmed: bool
    reopened: bool


class Statistics(BaseModel):
    date_from: date
    date_to: date
    generated_at: datetime
    total: int
    answered: int
    unanswered: int
    overdue: int
    confirmed: int
    awaiting_confirmation: int
    rejected: int
    reopened: int
    confirmed_percent: float | None
    average_first_response_hours: float | None
    kinds: list[CountItem]
    categories: list[CountItem]
    trend: list[TrendItem]
    topics: list[TopicPublic]
    appeals: list[StatisticAppeal]


@router.get("/statistics")
def statistics(
    actor: InsightReader,
    db: Db,
    date_from: date | None = None,
    date_to: date | None = None,
    utc_offset_minutes: Annotated[int, Query(ge=-840, le=840)] = 0,
    company_id: UUID | None = None,
    department_id: UUID | None = None,
) -> Statistics:
    now = utcnow()
    offset = timedelta(minutes=utc_offset_minutes)
    local_today = (now + offset).date()
    end = date_to or local_today
    start = date_from or (end - timedelta(days=29))
    if start > end or (end - start).days > 365:
        raise HTTPException(422, "Выберите период от 1 до 366 дней")
    if end > local_today:
        raise HTTPException(422, "Конец периода не может быть в будущем")
    since = datetime.combine(start, time.min, UTC) - offset
    until = datetime.combine(end + timedelta(days=1), time.min, UTC) - offset
    conditions = [Appeal.created_at >= since, Appeal.created_at < until]
    if "coordinator" not in actor.roles:
        conditions.append(Appeal.company_id == actor.company_id)
    if company_id is not None:
        conditions.append(Appeal.company_id == company_id)
    if department_id is not None:
        conditions.append(Appeal.department_id == department_id)
    appeals = list(
        db.exec(
            select(Appeal)
            .where(*conditions)
            .order_by(Appeal.created_at.desc(), Appeal.id.desc())
        ).all()
    )
    ids = [item.id for item in appeals]
    feedback = (
        list(
            db.exec(
                select(AppealFeedback).where(AppealFeedback.appeal_id.in_(ids))
            ).all()
        )
        if ids
        else []
    )
    helped = {item.appeal_id for item in feedback if item.outcome == "helped"}
    reopened = {item.appeal_id for item in feedback if item.outcome == "reopen"}
    confirmations = {}
    for item in feedback:
        if item.outcome == "helped":
            confirmations[item.appeal_id] = max(
                confirmations.get(item.appeal_id, item.created_at), item.created_at
            )
    items = [
        StatisticAppeal(
            **brief(item).model_dump(),
            kind=item.kind,
            category=item.category,
            company_id=item.company_id,
            department_id=item.department_id,
            first_response_at=item.first_response_at,
            overdue=item.next_response_at is not None
            and item.next_response_at < now
            and item.status not in {"closed", "rejected"},
            confirmed=item.status == "closed" and item.id in helped,
            reopened=item.id in reopened,
        )
        for item in appeals
    ]
    response_hours = [
        (item.first_response_at - item.created_at).total_seconds() / 3600
        for item in appeals
        if item.first_response_at is not None
        and item.first_response_at >= item.created_at
    ]
    confirmed_ids = {item.id for item in items if item.confirmed}
    received_days = Counter((item.created_at + offset).date() for item in appeals)
    confirmed_days = Counter(
        (confirmations[key] + offset).date() for key in confirmed_ids
    )
    # At most 53 weekly buckets; actual dates and values also form a readable table.
    trend = []
    cursor = start
    while cursor <= end:
        days = [
            cursor + timedelta(days=n) for n in range(min(7, (end - cursor).days + 1))
        ]
        trend.append(
            TrendItem(
                date=cursor,
                received=sum(received_days[d] for d in days),
                confirmed=sum(confirmed_days[d] for d in days),
            )
        )
        cursor += timedelta(days=7)
    kinds, categories = (
        Counter(item.kind for item in appeals),
        Counter(item.category for item in appeals),
    )
    return Statistics(
        date_from=start,
        date_to=end,
        generated_at=now,
        total=len(items),
        answered=len(response_hours),
        unanswered=len(items) - len(response_hours),
        overdue=sum(item.overdue for item in items),
        confirmed=len(confirmed_ids),
        awaiting_confirmation=sum(
            item.status == "awaiting_confirmation" for item in items
        ),
        rejected=sum(item.status == "rejected" for item in items),
        reopened=len(reopened),
        confirmed_percent=round(len(confirmed_ids) * 100 / len(items), 1)
        if items
        else None,
        average_first_response_hours=round(sum(response_hours) / len(response_hours), 2)
        if response_hours
        else None,
        kinds=[CountItem(key=key, count=kinds[key]) for key in ["problem", "idea"]],
        categories=[
            CountItem(key=key, count=value) for key, value in categories.most_common()
        ],
        trend=trend,
        topics=topic_groups(db, appeals),
        appeals=items,
    )
