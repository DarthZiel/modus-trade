from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

AppealKind = Literal["problem", "idea"]
Category = Literal["warehouse", "sales", "process", "workplace", "other"]
AppealStatus = Literal[
    "received",
    "reviewing",
    "needs_info",
    "in_progress",
    "awaiting_confirmation",
    "closed",
    "rejected",
]
ListFilter = Literal["all", "active", "needs_reply", "completed"]


class AppealInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    kind: AppealKind
    title: str = Field(min_length=5, max_length=160)
    description: str = Field(min_length=10, max_length=10000)
    category: Category = "other"
    original_description: str | None = Field(
        default=None, min_length=10, max_length=10000
    )
    submission_id: UUID


class AttachmentPublic(BaseModel):
    id: UUID
    filename: str
    media_type: str
    size: int
    download_url: str


class EventPublic(BaseModel):
    id: UUID
    text: str
    actor: str
    created_at: datetime


class AppealSummary(BaseModel):
    id: int
    number: str
    kind: AppealKind
    title: str
    category: Category
    status: AppealStatus
    responsible: str | None
    responsible_id: UUID | None
    responsible_available: bool | None
    assignment_version: int
    author: str
    author_id: UUID
    company: str
    department: str
    company_id: UUID
    department_id: UUID
    is_overdue: bool
    next_response_at: datetime | None
    created_at: datetime
    attachment_count: int
    supporters: int = 0


class FeedbackPublic(BaseModel):
    id: UUID
    outcome: Literal["helped", "reopen"]
    comment: str
    result_snapshot: str
    author: str
    created_at: datetime


class SupporterPublic(BaseModel):
    name: str
    department: str
    comment: str
    created_at: datetime


class AppealDetail(AppealSummary):
    original_description: str
    decision: str | None
    result: str | None
    decided_at: datetime | None
    description: str
    author: str
    company: str
    department: str
    attachments: list[AttachmentPublic]
    history: list[EventPublic]
    feedback: list[FeedbackPublic]
    supporters_list: list[SupporterPublic] = []


class AppealPage(BaseModel):
    items: list[AppealSummary]
    total: int
    page: int
    page_size: int


class AssignmentInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    responsible_id: UUID
    next_response_at: AwareDatetime
    expected_version: int = Field(ge=0)
    reason: str = Field(default="", max_length=1000)


class ResponsiblePublic(BaseModel):
    id: UUID
    name: str
    company: str
    department: str


class MessageInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    client_id: UUID
    body: str = Field(min_length=1, max_length=10000)


class MessagePublic(BaseModel):
    id: int
    sender_id: UUID
    sender: str
    is_author: bool
    body: str
    kind: str
    created_at: datetime


class MessagePage(BaseModel):
    items: list[MessagePublic]
    has_more: bool


class MessageSent(BaseModel):
    message: MessagePublic
    appeal: AppealDetail


class ReviewInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    action: Literal["start", "request_info", "resolve", "reject"]
    expected_version: int = Field(ge=0)
    explanation: str = Field(default="", max_length=10000)


class FeedbackInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    client_id: UUID
    outcome: Literal["helped", "reopen"]
    comment: str = Field(default="", max_length=10000)
    expected_version: int = Field(ge=0)
