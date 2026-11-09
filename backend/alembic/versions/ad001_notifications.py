"""Persistent notifications and reminder deduplication."""

import sqlalchemy as sa
from alembic import op

revision = "ad001"
down_revision = "9c001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "notifications",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "appeal_id", sa.Integer(), sa.ForeignKey("appeals.id"), nullable=False
        ),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("dedupe_key", sa.String(200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("user_id", "dedupe_key"),
    )
    op.create_index("ix_notifications_user_id", "notifications", ["user_id"])
    op.create_index("ix_notifications_appeal_id", "notifications", ["appeal_id"])


def downgrade():
    op.drop_table("notifications")
