"""Similar-appeal search (pg_trgm) and employees joining an existing appeal."""

import sqlalchemy as sa
from alembic import op

revision = "dg001"
down_revision = "cf001"
branch_labels = None
depends_on = None


def upgrade():
    # pg_trgm is a trusted extension (PostgreSQL 13+): the database owner may create it.
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute(
        "CREATE INDEX ix_appeals_title_trgm ON appeals "
        "USING gin (lower(title) gin_trgm_ops)"
    )
    op.create_table(
        "appeal_supporters",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "appeal_id", sa.Integer(), sa.ForeignKey("appeals.id"), nullable=False
        ),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("comment", sa.String(1000), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("appeal_id", "user_id"),
    )
    op.create_index(
        "ix_appeal_supporters_appeal_id", "appeal_supporters", ["appeal_id"]
    )
    op.create_index("ix_appeal_supporters_user_id", "appeal_supporters", ["user_id"])


def downgrade():
    op.drop_table("appeal_supporters")
    op.execute("DROP INDEX IF EXISTS ix_appeals_title_trgm")
