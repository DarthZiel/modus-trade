"""Version assignment changes to reject stale coordinator edits."""

import sqlalchemy as sa
from alembic import op

revision = "7a001"
down_revision = "6c999ff3885a"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "appeals",
        sa.Column(
            "assignment_version",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )


def downgrade():
    op.drop_column("appeals", "assignment_version")
