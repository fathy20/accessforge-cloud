"""Add relational indexes, uniqueness guarantees, and project location fields.

Every hot list endpoint filters on a foreign-key column that had no index
(jobs.user_id, uploads.user_id, notifications.user_id, audit_log.ts, ...).
user_roles and module_access additionally allowed duplicate assignment rows,
which the last-super-admin arithmetic and per-user module disable flags both
quietly depend on being unique.

Uniqueness is expressed as unique INDEXES (not table constraints) because
SQLite cannot ADD CONSTRAINT without a table rebuild, while both SQLite and
SQL Server create unique indexes in place.

THIS MIGRATION DELETES ROWS. Run these audits first and record the output;
a COUNT(*)-only audit is not sufficient, because it cannot show whether a
duplicate group disagrees about access. `downgrade()` cannot bring deleted
rows back -- the pre-migration backup is the only recovery path.

    -- 1. module_access groups that DISAGREE about access. Each row printed
    --    here is an access decision the migration will resolve. Per the
    --    2026-08-19 owner ruling the deny row survives; review the list and
    --    confirm that is correct for every group before proceeding.
    SELECT ma.user_id, ma.module_id, ma.id, ma.enabled, ma.granted_by, ma.created_at
    FROM module_access ma
    JOIN (
        SELECT user_id, module_id
        FROM module_access
        GROUP BY user_id, module_id
        HAVING COUNT(*) > 1
           AND MIN(CASE WHEN enabled = 0 THEN 0 ELSE 1 END)
             < MAX(CASE WHEN enabled = 0 THEN 0 ELSE 1 END)
    ) conflicting
      ON conflicting.user_id = ma.user_id
     AND conflicting.module_id = ma.module_id
    ORDER BY ma.user_id, ma.module_id, ma.id;

    -- 2. module_access duplicates that AGREE (informational; any survivor is
    --    equivalent, so these need no review).
    SELECT user_id, module_id, COUNT(*) AS n
    FROM module_access
    GROUP BY user_id, module_id
    HAVING COUNT(*) > 1
       AND MIN(CASE WHEN enabled = 0 THEN 0 ELSE 1 END)
         = MAX(CASE WHEN enabled = 0 THEN 0 ELSE 1 END);

    -- 3. user_roles duplicates (rows are interchangeable; counts suffice).
    SELECT user_id, role, COUNT(*) AS n
    FROM user_roles GROUP BY user_id, role HAVING COUNT(*) > 1;

    -- 4. add_column pre-flight: both must return no rows, or the migration
    --    aborts partway. Relevant because the baseline was adopted from an
    --    existing SQL Server database (see backend/tools/db_adopt.py).
    SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_NAME = 'projects' AND COLUMN_NAME IN ('tail_number', 'station');
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

    # Deduplicate before enforcing uniqueness. The two tables need DIFFERENT
    # survivor rules, and the difference is deliberate -- do not unify them.
    #
    # user_roles: a duplicate group is (id, user_id, role) and nothing else, so
    # the rows are genuinely interchangeable. Lowest id is fine.
    op.execute(
        "DELETE FROM user_roles WHERE id NOT IN "
        "(SELECT MIN(id) FROM user_roles GROUP BY user_id, role)"
    )

    # module_access: duplicates are NOT interchangeable -- they carry enabled,
    # granted_by and created_at. Picking by MIN(id) selects on a String(36)
    # UUID, i.e. alphabetically, so a group holding both an allow and a deny
    # row resolved arbitrarily; roughly half the time the migration GRANTED
    # access a user had been explicitly DENIED, and deleted the evidence.
    #
    # Owner ruling (Q-2, 2026-08-19): the most restrictive row wins. A
    # migration must never grant access someone was explicitly denied.
    #
    # "Restrictive" means enabled = 0 exactly, because that is the only thing
    # the application treats as a denial: _module_visibility_inputs filters on
    # `ModuleAccess.enabled == False` (backend/main.py), which never matches
    # NULL. So NULL groups with True as permissive rather than being invented
    # into a third meaning.
    #
    # Portability notes: the tier is a CASE expression rather than MIN(enabled)
    # because SQL Server rejects MIN() over a bit column. The NULL-safe join
    # predicates preserve GROUP BY's NULL-grouping, so rows with a NULL user_id
    # or module_id still collapse to one survivor instead of all being deleted.
    # MIN(id) now only breaks ties inside the winning tier, so the result stays
    # deterministic.
    op.execute(
        "DELETE FROM module_access WHERE id NOT IN ("
        " SELECT MIN(m.id) FROM module_access AS m"
        " WHERE (CASE WHEN m.enabled = 0 THEN 0 ELSE 1 END) = ("
        "  SELECT MIN(CASE WHEN m2.enabled = 0 THEN 0 ELSE 1 END)"
        "  FROM module_access AS m2"
        "  WHERE (m2.user_id = m.user_id OR (m2.user_id IS NULL AND m.user_id IS NULL))"
        "    AND (m2.module_id = m.module_id OR (m2.module_id IS NULL AND m.module_id IS NULL))"
        " )"
        " GROUP BY m.user_id, m.module_id"
        ")"
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
