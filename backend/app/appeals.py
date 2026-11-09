import hashlib
import json
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse
from pydantic import ValidationError
from sqlalchemy import func, text
from sqlmodel import select
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile

from app.appeal_schemas import (
    AppealDetail,
    AppealInput,
    AppealPage,
    AppealSummary,
    AttachmentPublic,
    EventPublic,
    FeedbackPublic,
    ListFilter,
)
from app.config import settings
from app.models import (
    Appeal,
    AppealAttachment,
    AppealEvent,
    AppealFeedback,
    Company,
    Department,
    User,
    utcnow,
)
from app.notifications import announce
from app.security import CurrentUser, Db
from app.uploads import MAX_FILES, StagedUploads

router = APIRouter(prefix="/appeals", tags=["Appeals"])


def accessible(appeal: Appeal | None, user: User) -> Appeal:
    if not appeal or not (
        appeal.author_id == user.id
        or "coordinator" in user.roles
        or ("responsible" in user.roles and appeal.responsible_id == user.id)
    ):
        # Do not disclose whether another employee's appeal exists.
        raise HTTPException(404, "Обращение не найдено")
    return appeal


def summary(appeal: Appeal, db, attachment_count: int) -> AppealSummary:
    responsible = db.get(User, appeal.responsible_id) if appeal.responsible_id else None
    return AppealSummary(
        id=appeal.id,
        number=f"MT-{appeal.id:06d}",
        kind=appeal.kind,
        title=appeal.title,
        category=appeal.category,
        status=appeal.status,
        responsible=responsible.name if responsible else None,
        responsible_id=appeal.responsible_id,
        responsible_available=(
            responsible.is_active and "responsible" in responsible.roles
        )
        if responsible
        else None,
        assignment_version=appeal.assignment_version,
        author=db.get(User, appeal.author_id).name,
        author_id=appeal.author_id,
        company=db.get(Company, appeal.company_id).name,
        department=db.get(Department, appeal.department_id).name,
        company_id=appeal.company_id,
        department_id=appeal.department_id,
        is_overdue=bool(
            appeal.next_response_at
            and appeal.next_response_at < utcnow()
            and appeal.status not in {"closed", "rejected"}
        ),
        next_response_at=appeal.next_response_at,
        created_at=appeal.created_at,
        attachment_count=attachment_count,
    )


def detail(appeal: Appeal, db) -> AppealDetail:
    files = db.exec(
        select(AppealAttachment).where(AppealAttachment.appeal_id == appeal.id)
    ).all()
    events = db.exec(
        select(AppealEvent)
        .where(AppealEvent.appeal_id == appeal.id)
        .order_by(AppealEvent.created_at, AppealEvent.id)
    ).all()
    return AppealDetail(
        **summary(appeal, db, len(files)).model_dump(),
        description=appeal.description,
        original_description=appeal.original_description,
        decision=appeal.decision,
        result=appeal.result,
        decided_at=appeal.decided_at,
        attachments=[
            AttachmentPublic(
                id=item.id,
                filename=item.filename,
                media_type=item.media_type,
                size=item.size,
                download_url=f"/api/appeals/{appeal.id}/attachments/{item.id}",
            )
            for item in files
        ],
        feedback=[
            FeedbackPublic(
                id=item.id,
                outcome=item.outcome,
                comment=item.comment,
                result_snapshot=item.result_snapshot,
                author=db.get(User, item.author_id).name,
                created_at=item.created_at,
            )
            for item in db.exec(
                select(AppealFeedback)
                .where(AppealFeedback.appeal_id == appeal.id)
                .order_by(AppealFeedback.created_at, AppealFeedback.id)
            ).all()
        ],
        history=[
            EventPublic(
                id=event.id,
                text=event.text,
                actor=db.get(User, event.actor_id).name,
                created_at=event.created_at,
            )
            for event in events
        ],
    )


def save_appeal(
    data: AppealInput, uploads: list[UploadFile], user: User, db, response: Response
) -> AppealDetail:
    # A retry or double-click must not create another appeal, including concurrent requests.
    db.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:key))"),
        {"key": f"appeal:{user.id}:{data.submission_id}"},
    )
    with StagedUploads(settings.upload_dir, uploads) as staged:
        payload = {
            **data.model_dump(mode="json"),
            "files": [
                {key: item[key] for key in ("filename", "size", "sha256")}
                for item in staged.items
            ],
        }
        payload_hash = hashlib.sha256(
            json.dumps(payload, sort_keys=True).encode()
        ).hexdigest()
        existing = db.exec(
            select(Appeal).where(
                Appeal.author_id == user.id, Appeal.submission_id == data.submission_id
            )
        ).first()
        if existing:
            if existing.payload_hash != payload_hash:
                raise HTTPException(
                    409,
                    "С этим ключом уже отправлено другое обращение. Откройте его в списке.",
                )
            response.status_code = 200
            return detail(existing, db)
        appeal = Appeal(
            **data.model_dump(exclude={"original_description"}),
            payload_hash=payload_hash,
            original_description=data.original_description or data.description,
            author_id=user.id,
            company_id=user.company_id,
            department_id=user.department_id,
        )
        try:
            db.add(appeal)
            db.flush()
            destination = staged.publish()
            for item in staged.items:
                db.add(
                    AppealAttachment(
                        appeal_id=appeal.id,
                        filename=item["filename"],
                        media_type=item["media_type"],
                        size=item["size"],
                        storage_key=f"{destination.name}/{item['name']}",
                    )
                )
            db.add(
                AppealEvent(
                    appeal_id=appeal.id, actor_id=user.id, text="Обращение отправлено"
                )
            )
            announce(db, appeal, "received", "Обращение принято")
            db.commit()
        except BaseException:
            db.rollback()
            raise
    return detail(appeal, db)


@router.post("", status_code=201)
async def create_appeal(
    request: Request, response: Response, user: CurrentUser, db: Db
) -> AppealDetail:
    if (
        not request.headers.get("content-type", "")
        .lower()
        .startswith("multipart/form-data")
    ):
        raise HTTPException(415, "Используйте форму multipart/form-data")
    async with request.form(
        max_files=MAX_FILES, max_fields=6, max_part_size=32 * 1024
    ) as form:
        files = form.getlist("files")
        if any(not isinstance(file, UploadFile) for file in files):
            raise HTTPException(422, "Некорректные вложения")
        try:
            data = AppealInput.model_validate(
                {key: value for key, value in form.items() if key != "files"}
            )
        except ValidationError as error:
            raise HTTPException(
                422, detail=error.errors(include_context=False, include_input=False)
            ) from None
        return await run_in_threadpool(save_appeal, data, files, user, db, response)


@router.get("")
def list_appeals(
    user: CurrentUser,
    db: Db,
    filter: ListFilter = "all",
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=50)] = 20,
) -> AppealPage:
    # This is always "my appeals", even for a coordinator; the shared queue is separate.
    conditions = [Appeal.author_id == user.id]
    if filter == "active":
        conditions.append(Appeal.status.notin_(["closed", "rejected"]))
    elif filter == "needs_reply":
        conditions.append(Appeal.status.in_(["needs_info", "awaiting_confirmation"]))
    elif filter == "completed":
        conditions.append(Appeal.status.in_(["closed", "rejected"]))
    total = db.exec(select(func.count()).select_from(Appeal).where(*conditions)).one()
    attachment_count = (
        select(AppealAttachment.appeal_id, func.count().label("count"))
        .group_by(AppealAttachment.appeal_id)
        .subquery()
    )
    rows = db.exec(
        select(Appeal, func.coalesce(attachment_count.c.count, 0))
        .outerjoin(attachment_count, attachment_count.c.appeal_id == Appeal.id)
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


@router.get("/{appeal_id}")
def get_appeal(appeal_id: int, user: CurrentUser, db: Db) -> AppealDetail:
    return detail(accessible(db.get(Appeal, appeal_id), user), db)


@router.get("/{appeal_id}/attachments/{attachment_id}")
def download_attachment(
    appeal_id: int, attachment_id: UUID, user: CurrentUser, db: Db
) -> FileResponse:
    accessible(db.get(Appeal, appeal_id), user)
    attachment = db.get(AppealAttachment, attachment_id)
    if not attachment or attachment.appeal_id != appeal_id:
        raise HTTPException(404, "Вложение не найдено")
    root = settings.upload_dir.resolve()
    path = (root / attachment.storage_key).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise HTTPException(404, "Файл недоступен")
    return FileResponse(
        path,
        filename=attachment.filename,
        media_type=attachment.media_type,
        content_disposition_type="attachment",
        headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "no-store"},
    )
