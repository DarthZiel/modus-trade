from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    Column,
    DateTime,
    Index,
    Integer,
    UniqueConstraint,
    func,
    text,
)
from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(UTC)


def timestamp():
    return Column(DateTime(timezone=True), nullable=False)


class Company(SQLModel, table=True):
    __tablename__ = "companies"
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    name: str = Field(max_length=160, unique=True)


class Department(SQLModel, table=True):
    __tablename__ = "departments"
    __table_args__ = (UniqueConstraint("company_id", "name"),)
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    company_id: UUID = Field(foreign_key="companies.id", index=True)
    name: str = Field(max_length=160)


class User(SQLModel, table=True):
    __tablename__ = "users"
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    name: str = Field(max_length=160)
    email: str = Field(max_length=254, unique=True)
    password_hash: str
    company_id: UUID = Field(foreign_key="companies.id")
    department_id: UUID = Field(foreign_key="departments.id")
    roles: list[str] = Field(
        default_factory=lambda: ["employee"], sa_column=Column(JSON, nullable=False)
    )
    is_active: bool = True
    created_at: datetime = Field(default_factory=utcnow, sa_column=timestamp())


class Invitation(SQLModel, table=True):
    __tablename__ = "invitations"
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    token_hash: str = Field(unique=True)
    name: str = Field(max_length=160)
    email: str = Field(max_length=254, index=True)
    company_id: UUID = Field(foreign_key="companies.id")
    department_id: UUID = Field(foreign_key="departments.id")
    roles: list[str] = Field(sa_column=Column(JSON, nullable=False))
    created_by: UUID = Field(foreign_key="users.id")
    created_at: datetime = Field(default_factory=utcnow, sa_column=timestamp())
    expires_at: datetime = Field(sa_column=timestamp())
    used_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True))
    )
    revoked_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True))
    )


class LoginSession(SQLModel, table=True):
    __tablename__ = "login_sessions"
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    telegram_id: int | None = Field(default=None, sa_column=Column(BigInteger))
    token_hash: str = Field(unique=True)
    user_id: UUID = Field(foreign_key="users.id", index=True)
    expires_at: datetime = Field(sa_column=timestamp())
    created_at: datetime = Field(default_factory=utcnow, sa_column=timestamp())


class Appeal(SQLModel, table=True):
    __tablename__ = "appeals"
    __table_args__ = (UniqueConstraint("author_id", "submission_id"),)
    id: int | None = Field(default=None, primary_key=True)
    submission_id: UUID
    assignment_version: int = Field(
        default=0, sa_column=Column(Integer, nullable=False, server_default=text("0"))
    )
    payload_hash: str
    kind: str = Field(max_length=16)
    title: str = Field(max_length=160)
    description: str = Field(max_length=10000)
    original_description: str = Field(max_length=10000)
    category: str = Field(max_length=32)
    author_id: UUID = Field(foreign_key="users.id", index=True)
    company_id: UUID = Field(foreign_key="companies.id")
    department_id: UUID = Field(foreign_key="departments.id")
    status: str = Field(default="received", max_length=32, index=True)
    resume_status: str | None = Field(default=None, max_length=32)
    decision: str | None = None
    result: str | None = None
    decided_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True))
    )
    responsible_id: UUID | None = Field(default=None, foreign_key="users.id")
    first_response_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True))
    )
    next_response_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True))
    )
    created_at: datetime = Field(default_factory=utcnow, sa_column=timestamp())


Index(
    "ix_appeals_title_trgm",
    func.lower(Appeal.title).label("title_normalized"),
    postgresql_using="gin",
    postgresql_ops={"title_normalized": "gin_trgm_ops"},
)


class AppealPriority(SQLModel, table=True):
    __tablename__ = "appeal_priorities"
    appeal_id: int = Field(foreign_key="appeals.id", primary_key=True)
    version: int = 0
    ai_lane: str | None = Field(default=None, max_length=16)
    ai_level: str | None = Field(default=None, max_length=16)
    ai_reason: str = Field(default="", max_length=1200)
    ai_next_step: str = Field(default="", max_length=600)
    ai_source: str = Field(default="", max_length=16)
    ai_context_hash: str = Field(default="", max_length=64)
    ai_updated_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True))
    )
    manual_lane: str | None = Field(default=None, max_length=16)
    manual_level: str | None = Field(default=None, max_length=16)
    manual_reason: str = Field(default="", max_length=1200)
    manual_next_step: str = Field(default="", max_length=600)
    manual_by: UUID | None = Field(default=None, foreign_key="users.id")
    manual_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True))
    )


class PriorityEvent(SQLModel, table=True):
    __tablename__ = "priority_events"
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    appeal_id: int = Field(foreign_key="appeals.id", index=True)
    actor_id: UUID = Field(foreign_key="users.id")
    action: str = Field(max_length=16)
    lane: str = Field(max_length=16)
    level: str = Field(max_length=16)
    reason: str = Field(max_length=1200)
    next_step: str = Field(max_length=600)
    source: str = Field(max_length=16)
    version: int
    created_at: datetime = Field(default_factory=utcnow, sa_column=timestamp())


class AppealRelation(SQLModel, table=True):
    __tablename__ = "appeal_relations"
    __table_args__ = (
        UniqueConstraint("left_id", "right_id"),
        CheckConstraint("left_id < right_id", name="ordered_pair"),
    )
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    left_id: int = Field(foreign_key="appeals.id", index=True)
    right_id: int = Field(foreign_key="appeals.id", index=True)
    kind: str = Field(max_length=32)
    topic: str = Field(max_length=160)
    reason: str = Field(max_length=1000)
    source: str = Field(max_length=16)
    status: str = Field(default="pending", max_length=16)
    version: int = 0
    reviewed_by: UUID | None = Field(default=None, foreign_key="users.id")
    created_at: datetime = Field(default_factory=utcnow, sa_column=timestamp())
    reviewed_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True))
    )


class AppealAttachment(SQLModel, table=True):
    __tablename__ = "appeal_attachments"
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    appeal_id: int = Field(foreign_key="appeals.id", index=True)
    filename: str = Field(max_length=255)
    storage_key: str
    media_type: str = Field(max_length=100)
    size: int


class AppealEvent(SQLModel, table=True):
    __tablename__ = "appeal_events"
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    appeal_id: int = Field(foreign_key="appeals.id", index=True)
    actor_id: UUID = Field(foreign_key="users.id")
    text: str
    created_at: datetime = Field(default_factory=utcnow, sa_column=timestamp())


class AppealSupporter(SQLModel, table=True):
    """An employee who joined an existing appeal instead of filing a duplicate."""

    __tablename__ = "appeal_supporters"
    __table_args__ = (UniqueConstraint("appeal_id", "user_id"),)
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    appeal_id: int = Field(foreign_key="appeals.id", index=True)
    user_id: UUID = Field(foreign_key="users.id", index=True)
    comment: str = Field(default="", max_length=1000)
    created_at: datetime = Field(default_factory=utcnow, sa_column=timestamp())


class AppealMessage(SQLModel, table=True):
    __tablename__ = "appeal_messages"
    __table_args__ = (UniqueConstraint("appeal_id", "sender_id", "client_id"),)
    id: int | None = Field(default=None, primary_key=True)
    appeal_id: int = Field(foreign_key="appeals.id", index=True)
    sender_id: UUID = Field(foreign_key="users.id")
    client_id: UUID
    body: str = Field(max_length=10000)
    kind: str = Field(default="message", max_length=32)
    created_at: datetime = Field(default_factory=utcnow, sa_column=timestamp())


class AppealFeedback(SQLModel, table=True):
    __tablename__ = "appeal_feedback"
    __table_args__ = (UniqueConstraint("author_id", "client_id"),)
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    appeal_id: int = Field(foreign_key="appeals.id", index=True)
    author_id: UUID = Field(foreign_key="users.id")
    client_id: UUID
    outcome: str = Field(max_length=16)
    comment: str = Field(max_length=10000)
    result_snapshot: str
    created_at: datetime = Field(default_factory=utcnow, sa_column=timestamp())


class Notification(SQLModel, table=True):
    __tablename__ = "notifications"
    __table_args__ = (UniqueConstraint("user_id", "dedupe_key"),)
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(foreign_key="users.id", index=True)
    appeal_id: int = Field(foreign_key="appeals.id", index=True)
    kind: str = Field(max_length=32)
    title: str = Field(max_length=200)
    telegram_sent_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True))
    )
    telegram_lease_until: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True))
    )
    telegram_link_id: UUID | None = None
    telegram_claim: UUID | None = None
    telegram_attempts: int = 0
    dedupe_key: str = Field(max_length=200)
    created_at: datetime = Field(default_factory=utcnow, sa_column=timestamp())
    read_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True))
    )


class TelegramLink(SQLModel, table=True):
    __tablename__ = "telegram_links"
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(foreign_key="users.id", unique=True)
    telegram_id: int = Field(sa_column=Column(BigInteger, nullable=False, unique=True))
    created_at: datetime = Field(default_factory=utcnow, sa_column=timestamp())
    delivery_enabled: bool = True
    state: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))


class TelegramLinkToken(SQLModel, table=True):
    __tablename__ = "telegram_link_tokens"
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(foreign_key="users.id", index=True)
    token_hash: str = Field(unique=True)
    expires_at: datetime = Field(sa_column=timestamp())


class Experiment(SQLModel, table=True):
    __tablename__ = "experiments"
    __table_args__ = (
        UniqueConstraint("created_by", "client_id"),
        Index(
            "uq_experiments_active_appeal",
            "appeal_id",
            unique=True,
            postgresql_where=text("status = 'active'"),
        ),
    )
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    appeal_id: int = Field(foreign_key="appeals.id", index=True)
    created_by: UUID = Field(foreign_key="users.id")
    client_id: UUID
    responsible_id: UUID = Field(foreign_key="users.id")
    hypothesis: str = Field(max_length=2000)
    change: str = Field(max_length=3000)
    success_criterion: str = Field(max_length=2000)
    planned_cost: str = Field(default="", max_length=1000)
    baseline: str = Field(default="", max_length=2000)
    metric: str = Field(default="", max_length=160)
    unit: str = Field(default="", max_length=80)
    before_value: float | None = None
    after_value: float | None = None
    starts_at: datetime = Field(sa_column=timestamp())
    ends_at: datetime = Field(sa_column=timestamp())
    status: str = Field(default="active", max_length=16)
    version: int = 0
    actions: str = Field(default="", max_length=3000)
    actual_cost: str = Field(default="", max_length=1000)
    observations: str = Field(default="", max_length=3000)
    author_comment: str = Field(default="", max_length=2000)
    outcome: str | None = Field(default=None, max_length=16)
    finished_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True))
    )
    created_at: datetime = Field(default_factory=utcnow, sa_column=timestamp())
