"""Director priorities with independent coordinator overrides and audit history."""

import sqlalchemy as sa
from alembic import op

revision = "e1001"
down_revision = "d1001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "appeal_priorities",
        sa.Column(
            "appeal_id", sa.Integer(), sa.ForeignKey("appeals.id"), primary_key=True
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        *[
            sa.Column(name, sa.String(16))
            for name in ["ai_lane", "ai_level", "manual_lane", "manual_level"]
        ],
        *[
            sa.Column(name, sa.String(length), nullable=False)
            for name, length in [
                ("ai_reason", 1200),
                ("ai_next_step", 600),
                ("ai_source", 16),
                ("ai_context_hash", 64),
                ("manual_reason", 1200),
                ("manual_next_step", 600),
            ]
        ],
        sa.Column("ai_updated_at", sa.DateTime(timezone=True)),
        sa.Column("manual_by", sa.Uuid(), sa.ForeignKey("users.id")),
        sa.Column("manual_at", sa.DateTime(timezone=True)),
    )
    op.create_table(
        "priority_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "appeal_id", sa.Integer(), sa.ForeignKey("appeals.id"), nullable=False
        ),
        sa.Column("actor_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        *[
            sa.Column(name, sa.String(length), nullable=False)
            for name, length in [
                ("action", 16),
                ("lane", 16),
                ("level", 16),
                ("reason", 1200),
                ("next_step", 600),
                ("source", 16),
            ]
        ],
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_priority_events_appeal_id", "priority_events", ["appeal_id"])


def downgrade():
    op.drop_table("priority_events")
    op.drop_table("appeal_priorities")
