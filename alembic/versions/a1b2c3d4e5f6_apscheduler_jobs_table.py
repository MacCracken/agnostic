"""Add APScheduler jobs table for persistent job store.

Revision ID: a1b2c3d4e5f6
Revises: db8d3fe1686e
Create Date: 2026-03-28 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: str | Sequence[str] | None = "db8d3fe1686e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "apscheduler_jobs",
        sa.Column("id", sa.Unicode(191), primary_key=True),
        sa.Column("next_run_time", sa.Float(25), index=True),
        sa.Column("job_state", sa.LargeBinary, nullable=False),
    )


def downgrade() -> None:
    op.drop_table("apscheduler_jobs")
