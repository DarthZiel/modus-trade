"""Author confirmation and returned results."""

import sqlalchemy as sa
from alembic import op

revision = "9c001"
down_revision = "8b001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "appeal_feedback",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "appeal_id", sa.Integer(), sa.ForeignKey("appeals.id"), nullable=False
        ),
        sa.Column("author_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("client_id", sa.Uuid(), nullable=False),
        sa.Column("outcome", sa.String(16), nullable=False),
        sa.Column("comment", sa.String(10000), nullable=False),
        sa.Column("result_snapshot", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("author_id", "client_id"),
    )
    op.create_index("ix_appeal_feedback_appeal_id", "appeal_feedback", ["appeal_id"])


def downgrade():
    op.drop_table("appeal_feedback")
