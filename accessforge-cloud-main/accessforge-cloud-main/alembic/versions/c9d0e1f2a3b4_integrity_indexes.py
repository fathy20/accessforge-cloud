"""Add relational indexes, uniqueness guarantees, and project location fields.

Every hot list endpoint filters on a foreign-key column that had no index
(jobs.user_id, uploads.user_id, notifications.user_id, audit_log.ts, ...).
user_roles and module_access additionally allowed duplicate assignment rows,
which the last-super-admin arithmetic and per-user module disable flags both
quietly depend on being unique.

Uniqueness is expressed as unique INDEXES (not table constraints) because
SQLite cannot ADD CONSTRAINT without a table rebuild, while both SQLite and
SQL Server create unique indexes in place.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c9d0e1f2a3b4"
down_revision: Union[str, Sequence[str], None] = "b8c9d0e1f2a3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


INDEXES: tuple[tuple[str, str, list[str]], ...] = (
    ("ix_jobs_user_id", "jobs", ["user_id"]),
    ("ix_uploads_user_id", "uploads", ["user_id"]),
    ("ix_notifications_user_id", "notifications", ["user_id"]),
    ("ix_audit_log_user_id", "audit_log", ["user_id"]),
    ("ix_audit_log_ts", "audit_log", ["ts"]),
    ("ix_module_access_user_id", "module_access", ["user_id"]),
    ("ix_module_access_module_id", "module_access", ["module_id"]),
    ("ix_user_roles_user_id", "user_roles", ["user_id"]),
    ("ix_projects_owner_id", "projects", ["owner_id"]),
)

# ix_-prefixed even though unique: the naming-convention gate requires every
# index (SQLite reports unique indexes as indexes) to carry the ix_ prefix.
UNIQUE_INDEXES: tuple[tuple[str, str, list[str]], ...] = (
    ("ix_user_roles_user_id_role", "user_roles", ["user_id", "role"]),
    ("ix_module_access_user_id_module_id", "module_access", ["user_id", "module_id"]),
)


def upgrade() -> None:
    # The projects UI has always submitted these two fields; the table never
    # had columns for them, so they were silently dropped.
    op.add_column("projects", sa.Column("tail_number", sa.String(length=64), nullable=True))
    op.add_column("projects", sa.Column("station", sa.String(length=64), nullable=True))

    # Deduplicate before enforcing uniqueness: keep one deterministic row
    # (lowest id) per duplicate group. Valid on both SQLite and SQL Server.
    op.execute(
        "DELETE FROM user_roles WHERE id NOT IN "
        "(SELECT MIN(id) FROM user_roles GROUP BY user_id, role)"
    )
    op.execute(
        "DELETE FROM module_access WHERE id NOT IN "
        "(SELECT MIN(id) FROM module_access GROUP BY user_id, module_id)"
    )

    for name, table, columns in INDEXES:
        op.create_index(name, table, columns, unique=False)
    for name, table, columns in UNIQUE_INDEXES:
        op.create_index(name, table, columns, unique=True)


def downgrade() -> None:
    for name, table, _columns in reversed(UNIQUE_INDEXES):
        op.drop_index(name, table_name=table)
    for name, table, _columns in reversed(INDEXES):
        op.drop_index(name, table_name=table)
    op.drop_column("projects", "station")
    op.drop_column("projects", "tail_number")
