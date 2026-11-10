"""Coordinator-reviewed similarities and durable first human response."""

import sqlalchemy as sa
from alembic import op

revision = "d1001"
down_revision = "cf001"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("appeals", sa.Column("first_response_at", sa.DateTime(timezone=True)))
    # Only evidence of a human message/question/decision; assignments and bot
    # receipts do not count. Missing historical evidence stays unknown.
    op.execute("""
        UPDATE appeals a SET first_response_at = r.at FROM (
            SELECT appeal_id, min(at) AS at FROM (
                SELECT m.appeal_id, m.created_at AS at
                FROM appeal_messages m JOIN appeals a ON a.id = m.appeal_id
                WHERE m.sender_id <> a.author_id
                UNION ALL
                SELECT e.appeal_id, e.created_at AS at
                FROM appeal_events e JOIN appeals a ON a.id = e.appeal_id
                WHERE e.actor_id <> a.author_id AND (
                    e.text LIKE 'Результат выполнения зафиксирован.%'
                    OR e.text LIKE 'Обращение отклонено.%'
                    OR e.text LIKE 'Запрошено уточнение у автора.%'
                )
            ) evidence GROUP BY appeal_id
        ) r WHERE a.id = r.appeal_id AND r.at >= a.created_at
    """)
    op.create_table(
        "appeal_relations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("left_id", sa.Integer(), sa.ForeignKey("appeals.id"), nullable=False),
        sa.Column(
            "right_id", sa.Integer(), sa.ForeignKey("appeals.id"), nullable=False
        ),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("topic", sa.String(160), nullable=False),
        sa.Column("reason", sa.String(1000), nullable=False),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("reviewed_by", sa.Uuid(), sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("left_id", "right_id"),
        sa.CheckConstraint("left_id < right_id", name="ordered_pair"),
    )
    op.create_index("ix_appeal_relations_left_id", "appeal_relations", ["left_id"])
    op.create_index("ix_appeal_relations_right_id", "appeal_relations", ["right_id"])


def downgrade():
    op.drop_table("appeal_relations")
    op.drop_column("appeals", "first_response_at")
