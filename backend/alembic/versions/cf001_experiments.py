"""Appeal experiments and recorded measurements."""

import sqlalchemy as sa
from alembic import op

revision = "cf001"
down_revision = "be001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "experiments",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "appeal_id", sa.Integer(), sa.ForeignKey("appeals.id"), nullable=False
        ),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("client_id", sa.Uuid(), nullable=False),
        sa.Column(
            "responsible_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False
        ),
        *[
            sa.Column(name, sa.String(length), nullable=False)
            for name, length in [
                ("hypothesis", 2000),
                ("change", 3000),
                ("success_criterion", 2000),
                ("planned_cost", 1000),
                ("baseline", 2000),
                ("metric", 160),
                ("unit", 80),
                ("status", 16),
                ("actions", 3000),
                ("actual_cost", 1000),
                ("observations", 3000),
                ("author_comment", 2000),
            ]
        ],
        sa.Column("outcome", sa.String(16), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("before_value", sa.Float(), nullable=True),
        sa.Column("after_value", sa.Float(), nullable=True),
        *[
            sa.Column(name, sa.DateTime(timezone=True), nullable=False)
            for name in ["starts_at", "ends_at", "created_at"]
        ],
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("created_by", "client_id"),
    )
    op.create_index("ix_experiments_appeal_id", "experiments", ["appeal_id"])
    op.create_index(
        "uq_experiments_active_appeal",
        "experiments",
        ["appeal_id"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )


def downgrade():
    op.drop_table("experiments")
