"""Appeal discussion and review decisions."""

import sqlalchemy as sa
from alembic import op

revision = "8b001"
down_revision = "7a001"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("appeals", sa.Column("resume_status", sa.String(32), nullable=True))
    op.add_column("appeals", sa.Column("decision", sa.String(), nullable=True))
    op.add_column("appeals", sa.Column("result", sa.String(), nullable=True))
    op.add_column(
        "appeals", sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_table(
        "appeal_messages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "appeal_id", sa.Integer(), sa.ForeignKey("appeals.id"), nullable=False
        ),
        sa.Column("sender_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("client_id", sa.Uuid(), nullable=False),
        sa.Column("body", sa.String(10000), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("appeal_id", "sender_id", "client_id"),
    )
    op.create_index("ix_appeal_messages_appeal_id", "appeal_messages", ["appeal_id"])


def downgrade():
    op.drop_table("appeal_messages")
    for column in ("decided_at", "result", "decision", "resume_status"):
        op.drop_column("appeals", column)
