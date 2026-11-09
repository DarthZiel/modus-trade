"""Telegram identity, single-use links and delivery leases."""

import sqlalchemy as sa
from alembic import op

revision = "be001"
down_revision = "ad001"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "login_sessions", sa.Column("telegram_id", sa.BigInteger(), nullable=True)
    )
    op.create_table(
        "telegram_links",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False, unique=True
        ),
        sa.Column("telegram_id", sa.BigInteger(), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("delivery_enabled", sa.Boolean(), nullable=False),
        sa.Column("state", sa.JSON(), nullable=False),
    )
    op.create_table(
        "telegram_link_tokens",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("token_hash", sa.String(), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_telegram_link_tokens_user_id", "telegram_link_tokens", ["user_id"]
    )
    for name in ["telegram_sent_at", "telegram_lease_until"]:
        op.add_column(
            "notifications", sa.Column(name, sa.DateTime(timezone=True), nullable=True)
        )
    op.add_column(
        "notifications", sa.Column("telegram_link_id", sa.Uuid(), nullable=True)
    )
    op.add_column(
        "notifications", sa.Column("telegram_claim", sa.Uuid(), nullable=True)
    )
    op.add_column(
        "notifications",
        sa.Column(
            "telegram_attempts", sa.Integer(), nullable=False, server_default="0"
        ),
    )
    op.alter_column("notifications", "telegram_attempts", server_default=None)


def downgrade():
    for name in [
        "telegram_sent_at",
        "telegram_lease_until",
        "telegram_claim",
        "telegram_link_id",
        "telegram_attempts",
    ]:
        op.drop_column("notifications", name)
    op.drop_table("telegram_link_tokens")
    op.drop_table("telegram_links")
    op.drop_column("login_sessions", "telegram_id")
