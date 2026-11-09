"""Closed-loop impact metrics: did the fix actually help, in the author's own words.

Everything is computed from recorded facts only (statuses, author feedback,
experiment measurements). Nothing is estimated: if an experiment has no
measurements, its effect is reported as unconfirmed.
"""

from collections import defaultdict
from datetime import datetime, timedelta
from statistics import median
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import or_
from sqlmodel import select

from app.models import (
    Appeal,
    AppealEvent,
    AppealFeedback,
    AppealSupporter,
    Department,
    Experiment,
    utcnow,
)
from app.security import Db
from app.work_queue import WorkUser

router = APIRouter(prefix="/work", tags=["Work queue"])

FINAL = {"closed", "rejected"}
CATEGORY = {
    "warehouse": "Склад и логистика",
    "sales": "Продажи и ассортимент",
    "process": "Рабочие инструменты и процессы",
    "workplace": "Условия труда",
    "other": "Другое",
}


class Funnel(BaseModel):
    received: int
    assigned: int
    result_reported: int
    confirmed: int


class Loop(BaseModel):
    ratings: int
    helped: int
    reopened: int
    helped_rate: float | None
    helped_first_time: int
    helped_after_rework: int
    awaiting: int
    rejected: int


class Timing(BaseModel):
    median_hours_to_assign: float | None
    median_days_to_result: float | None
    median_days_to_confirmed: float | None
    active: int
    overdue: int
    on_time_rate: float | None


class Breakdown(BaseModel):
    key: str
    label: str
    total: int
    active: int
    confirmed: int
    helped_rate: float | None
    supporters: int


class MeasuredExperiment(BaseModel):
    appeal_id: int
    number: str
    title: str
    metric: str
    unit: str
    before: float
    after: float
    outcome: str | None


class Experiments(BaseModel):
    total: int
    active: int
    finished: int
    outcomes: dict[str, int]
    measured: int
    unmeasured_finished: int
    examples: list[MeasuredExperiment]


class Supported(BaseModel):
    appeal_id: int
    number: str
    title: str
    status: str
    supporters: int


class Week(BaseModel):
    start: datetime
    created: int
    confirmed: int


class Metrics(BaseModel):
    period_days: int | None
    scope: Literal["all", "mine"]
    generated_at: datetime
    funnel: Funnel
    loop: Loop
    timing: Timing
    duplicates_prevented: int
    most_supported: list[Supported]
    categories: list[Breakdown]
    departments: list[Breakdown]
    experiments: Experiments
    weeks: list[Week]


def rate(part: int, whole: int) -> float | None:
    return round(part / whole, 3) if whole else None


def hours(start: datetime, end: datetime) -> float:
    return (end - start).total_seconds() / 3600


@router.get("/metrics")
def metrics(actor: WorkUser, db: Db, days: int = 0) -> Metrics:
    """Coordinators see the whole company group; a responsible sees own appeals."""
    now = utcnow()
    coordinator = "coordinator" in actor.roles
    conditions = [] if coordinator else [Appeal.responsible_id == actor.id]
    if days > 0:
        conditions.append(Appeal.created_at >= now - timedelta(days=days))
    appeals = db.exec(select(Appeal).where(*conditions)).all()
    ids = [item.id for item in appeals]
    by_id = {item.id: item for item in appeals}

    feedback = defaultdict(list)
    supporters = defaultdict(int)
    first_assign: dict[int, datetime] = {}
    experiments = []
    if ids:
        for item in db.exec(
            select(AppealFeedback)
            .where(AppealFeedback.appeal_id.in_(ids))
            .order_by(AppealFeedback.created_at)
        ).all():
            feedback[item.appeal_id].append(item)
        for item in db.exec(
            select(AppealSupporter).where(AppealSupporter.appeal_id.in_(ids))
        ).all():
            supporters[item.appeal_id] += 1
        for item in db.exec(
            select(AppealEvent)
            .where(
                AppealEvent.appeal_id.in_(ids),
                or_(
                    AppealEvent.text.startswith("Ответственный:"),
                    AppealEvent.text.startswith("Назначен ответственный"),
                ),
            )
            .order_by(AppealEvent.created_at)
        ).all():
            first_assign.setdefault(item.appeal_id, item.created_at)
        experiments = db.exec(
            select(Experiment).where(Experiment.appeal_id.in_(ids))
        ).all()

    def confirmed(appeal: Appeal) -> bool:
        return appeal.status == "closed"

    def reported(appeal: Appeal) -> bool:
        return bool(feedback[appeal.id]) or appeal.status in {
            "awaiting_confirmation",
            "closed",
        }

    ratings = [item for items in feedback.values() for item in items]
    helped = sum(item.outcome == "helped" for item in ratings)
    reopened = sum(item.outcome == "reopen" for item in ratings)
    closed = [item for item in appeals if confirmed(item)]
    active = [item for item in appeals if item.status not in FINAL]
    overdue = [
        item
        for item in active
        if item.next_response_at and item.next_response_at < now
    ]
    to_result = []
    for appeal in appeals:
        marks = [item.created_at for item in feedback[appeal.id]] + (
            [appeal.decided_at]
            if appeal.decided_at and appeal.status != "rejected"
            else []
        )
        if marks:
            to_result.append(hours(appeal.created_at, min(marks)) / 24)
    to_confirmed = [
        hours(
            appeal.created_at,
            next(
                item.created_at
                for item in reversed(feedback[appeal.id])
                if item.outcome == "helped"
            ),
        )
        / 24
        for appeal in closed
        if any(item.outcome == "helped" for item in feedback[appeal.id])
    ]
    to_assign = [
        hours(by_id[key].created_at, value) for key, value in first_assign.items()
    ]

    def breakdown(key_of, label_of) -> list[Breakdown]:
        groups = defaultdict(list)
        for appeal in appeals:
            groups[key_of(appeal)].append(appeal)
        result = []
        for key, items in groups.items():
            votes = [x for appeal in items for x in feedback[appeal.id]]
            result.append(
                Breakdown(
                    key=str(key),
                    label=label_of(key),
                    total=len(items),
                    active=sum(item.status not in FINAL for item in items),
                    confirmed=sum(confirmed(item) for item in items),
                    helped_rate=rate(
                        sum(x.outcome == "helped" for x in votes), len(votes)
                    ),
                    supporters=sum(supporters[item.id] for item in items),
                )
            )
        return sorted(result, key=lambda item: (-item.total, item.label))

    departments = {item.id: item.name for item in db.exec(select(Department)).all()}
    finished = [item for item in experiments if item.status == "completed"]
    measured = [
        item
        for item in finished
        if item.before_value is not None and item.after_value is not None
    ]
    outcomes = defaultdict(int)
    for item in finished:
        outcomes[item.outcome or "unknown"] += 1

    weeks = []
    start_of_week = (now - timedelta(days=now.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    for offset in range(7, -1, -1):
        start = start_of_week - timedelta(weeks=offset)
        end = start + timedelta(weeks=1)
        weeks.append(
            Week(
                start=start,
                created=sum(start <= item.created_at < end for item in appeals),
                confirmed=sum(
                    start <= x.created_at < end
                    for x in ratings
                    if x.outcome == "helped"
                ),
            )
        )

    return Metrics(
        period_days=days or None,
        scope="all" if coordinator else "mine",
        generated_at=now,
        funnel=Funnel(
            received=len(appeals),
            assigned=sum(
                item.responsible_id is not None or item.id in first_assign
                for item in appeals
            ),
            result_reported=sum(reported(item) for item in appeals),
            confirmed=len(closed),
        ),
        loop=Loop(
            ratings=len(ratings),
            helped=helped,
            reopened=reopened,
            helped_rate=rate(helped, len(ratings)),
            helped_first_time=sum(
                not any(x.outcome == "reopen" for x in feedback[item.id])
                for item in closed
            ),
            helped_after_rework=sum(
                any(x.outcome == "reopen" for x in feedback[item.id])
                for item in closed
            ),
            awaiting=sum(item.status == "awaiting_confirmation" for item in appeals),
            rejected=sum(item.status == "rejected" for item in appeals),
        ),
        timing=Timing(
            median_hours_to_assign=round(median(to_assign), 1) if to_assign else None,
            median_days_to_result=round(median(to_result), 1) if to_result else None,
            median_days_to_confirmed=round(median(to_confirmed), 1)
            if to_confirmed
            else None,
            active=len(active),
            overdue=len(overdue),
            on_time_rate=rate(len(active) - len(overdue), len(active)),
        ),
        duplicates_prevented=sum(supporters.values()),
        most_supported=[
            Supported(
                appeal_id=key,
                number=f"MT-{key:06d}",
                title=by_id[key].title,
                status=by_id[key].status,
                supporters=count,
            )
            for key, count in sorted(supporters.items(), key=lambda x: (-x[1], x[0]))[
                :5
            ]
        ],
        categories=breakdown(lambda a: a.category, lambda k: CATEGORY.get(k, k)),
        departments=breakdown(
            lambda a: a.department_id, lambda k: departments.get(k, "—")
        )[:8],
        experiments=Experiments(
            total=len(experiments),
            active=sum(item.status == "active" for item in experiments),
            finished=len(finished),
            outcomes=dict(outcomes),
            measured=len(measured),
            unmeasured_finished=len(finished) - len(measured),
            examples=[
                MeasuredExperiment(
                    appeal_id=item.appeal_id,
                    number=f"MT-{item.appeal_id:06d}",
                    title=by_id[item.appeal_id].title,
                    metric=item.metric,
                    unit=item.unit,
                    before=item.before_value,
                    after=item.after_value,
                    outcome=item.outcome,
                )
                for item in sorted(
                    measured, key=lambda x: x.finished_at or now, reverse=True
                )[:3]
            ],
        ),
        weeks=weeks,
    )
