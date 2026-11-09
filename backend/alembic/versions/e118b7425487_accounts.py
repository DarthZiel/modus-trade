"""accounts"""

import sqlalchemy as sa
from alembic import op

revision = "e118b7425487"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "companies",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_table(
        "departments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", "name"),
    )
    op.create_index(
        op.f("ix_departments_company_id"), "departments", ["company_id"], unique=False
    )
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("email", sa.String(length=254), nullable=False),
        sa.Column("password_hash", sa.String(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("department_id", sa.Uuid(), nullable=False),
        sa.Column("roles", sa.JSON(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
        ),
        sa.ForeignKeyConstraint(
            ["department_id"],
            ["departments.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )
    op.create_table(
        "invitations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("email", sa.String(length=254), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("department_id", sa.Uuid(), nullable=False),
        sa.Column("roles", sa.JSON(), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
        ),
        sa.ForeignKeyConstraint(
            ["department_id"],
            ["departments.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index(
        op.f("ix_invitations_email"), "invitations", ["email"], unique=False
    )
    op.create_table(
        "login_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index(
        op.f("ix_login_sessions_user_id"), "login_sessions", ["user_id"], unique=False
    )


def downgrade():
    op.drop_index(op.f("ix_login_sessions_user_id"), table_name="login_sessions")
    op.drop_table("login_sessions")
    op.drop_index(op.f("ix_invitations_email"), table_name="invitations")
    op.drop_table("invitations")
    op.drop_table("users")
    op.drop_index(op.f("ix_departments_company_id"), table_name="departments")
    op.drop_table("departments")
    op.drop_table("companies")
