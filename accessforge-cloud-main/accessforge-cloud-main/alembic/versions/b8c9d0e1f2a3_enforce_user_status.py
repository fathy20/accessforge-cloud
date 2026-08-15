"""Make user status non-null with an active server default."""

from typing import Sequence, Union

from alembic import context, op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b8c9d0e1f2a3"
down_revision: Union[str, Sequence[str], None] = "f7a8b9c0d1e2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


STATUS_TYPE = sa.String(length=24)
STATUS_DEFAULT = sa.text("'active'")


def _dialect_name() -> str:
    return op.get_bind().dialect.name


def _offline_mode() -> bool:
    return context.is_offline_mode()


def _alter_user_status(
    *,
    nullable: bool,
    existing_nullable: bool,
    server_default: sa.TextClause | None,
    existing_server_default: sa.TextClause | None,
) -> None:
    if _dialect_name() == "sqlite" and _offline_mode():
        op.alter_column(
            "users",
            "status",
            existing_type=STATUS_TYPE,
            existing_nullable=existing_nullable,
            nullable=nullable,
            server_default=server_default,
            existing_server_default=existing_server_default,
        )
        return

    if _dialect_name() == "sqlite":
        with op.batch_alter_table("users", recreate="always") as batch_op:
            batch_op.alter_column(
                "status",
                existing_type=STATUS_TYPE,
                existing_nullable=existing_nullable,
                nullable=nullable,
                server_default=server_default,
                existing_server_default=existing_server_default,
            )
        return

    if _dialect_name() == "mssql":
        op.alter_column(
            "users",
            "status",
            existing_type=STATUS_TYPE,
            existing_nullable=existing_nullable,
            nullable=nullable,
        )
        if nullable:
            op.execute(
                sa.text(
                    "IF EXISTS (\n"
                    "    SELECT 1 FROM sys.default_constraints\n"
                    "    WHERE parent_object_id = OBJECT_ID('users')\n"
                    "      AND col_name(parent_object_id, parent_column_id) = 'status'\n"
                    "      AND name = 'df_users_status'\n"
                    ")\n"
                    "ALTER TABLE users DROP CONSTRAINT df_users_status;"
                )
            )
        else:
            op.execute(
                sa.text(
                    "IF NOT EXISTS (\n"
                    "    SELECT 1 FROM sys.default_constraints\n"
                    "    WHERE parent_object_id = OBJECT_ID('users')\n"
                    "      AND col_name(parent_object_id, parent_column_id) = 'status'\n"
                    ")\n"
                    "ALTER TABLE users ADD CONSTRAINT df_users_status DEFAULT 'active' FOR status;"
                )
            )
        return

    op.alter_column(
        "users",
        "status",
        existing_type=STATUS_TYPE,
        existing_nullable=existing_nullable,
        nullable=nullable,
        server_default=server_default,
        existing_server_default=existing_server_default,
    )


def upgrade() -> None:
    op.execute(sa.text("UPDATE users SET status = 'active' WHERE status IS NULL"))
    _alter_user_status(
        nullable=False,
        existing_nullable=True,
        server_default=STATUS_DEFAULT,
        existing_server_default=None,
    )


def downgrade() -> None:
    _alter_user_status(
        nullable=True,
        existing_nullable=False,
        server_default=None,
        existing_server_default=STATUS_DEFAULT,
    )
