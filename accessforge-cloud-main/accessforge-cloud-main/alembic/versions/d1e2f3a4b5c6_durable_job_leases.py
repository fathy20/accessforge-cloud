"""Lease, fencing, attempt, and cancellation columns for durable job execution.

Jobs used to run inside the API process via BackgroundTasks: a restart lost
queued work, nothing could cancel a running job, and a heavy OCR job starved
request handling. The separate worker (``python -m worker.runner``) claims
rows from this table with an optimistic UPDATE and fences every later write
on ``lease_token``; these columns carry that state.

All new columns are nullable or carry a server default, so the migration is
online-safe for existing rows on both SQLite and SQL Server. The composite
index backs the worker's claim scan (queued or expired-running, oldest first).
"""

from typing import Sequence, Union

from alembic import context, op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d1e2f3a4b5c6"
down_revision: Union[str, Sequence[str], None] = "c9d0e1f2a3b4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

INDEX_NAME = "ix_jobs_status_created_at"


def _dialect_name() -> str:
    return op.get_bind().dialect.name


def _offline_mode() -> bool:
    return context.is_offline_mode()


def _job_columns() -> tuple[sa.Column, ...]:
    return (
        sa.Column("attempt", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("lease_owner", sa.String(length=128), nullable=True),
        sa.Column("lease_token", sa.String(length=36), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancel_requested", sa.Boolean(), nullable=False, server_default="0"),
    )


def upgrade() -> None:
    columns = _job_columns()

    if _dialect_name() == "sqlite" and not _offline_mode():
        with op.batch_alter_table("jobs", recreate="always") as batch_op:
            for column in columns:
                batch_op.add_column(column)
    else:
        for column in columns:
            op.add_column("jobs", column)

    op.create_index(INDEX_NAME, "jobs", ["status", "created_at"], unique=False)


def downgrade() -> None:
    op.drop_index(INDEX_NAME, table_name="jobs")

    column_names = (
        "cancel_requested",
        "heartbeat_at",
        "lease_expires_at",
        "lease_token",
        "lease_owner",
        "attempt",
    )

    if _dialect_name() == "sqlite" and not _offline_mode():
        with op.batch_alter_table("jobs", recreate="always") as batch_op:
            for column_name in column_names:
                batch_op.drop_column(column_name)
        return

    for column_name in column_names:
        if _dialect_name() == "mssql" and column_name in ("attempt", "cancel_requested"):
            # SQL Server refuses to drop a column while its default constraint
            # exists; Alembic drops the server-named constraint first.
            op.drop_column("jobs", column_name, mssql_drop_default=True)
        else:
            op.drop_column("jobs", column_name)
