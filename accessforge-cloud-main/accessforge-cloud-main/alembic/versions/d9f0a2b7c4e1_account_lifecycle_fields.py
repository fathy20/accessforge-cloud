"""Persist account login and password lifecycle state."""

from typing import Sequence, Union

from alembic import context, op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d9f0a2b7c4e1"
down_revision: Union[str, Sequence[str], None] = "c7e4a1b93d42"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _dialect_name() -> str:
    return op.get_bind().dialect.name


def _offline_mode() -> bool:
    return context.is_offline_mode()


def _user_columns() -> tuple[sa.Column, ...]:
    return (
        sa.Column(
            "failed_login_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("password_changed_at", sa.DateTime(timezone=True), nullable=True),
    )


def _add_user_columns() -> None:
    columns = _user_columns()

    if _dialect_name() == "sqlite" and _offline_mode():
        for column in columns:
            op.add_column("users", column)
        return

    if _dialect_name() == "sqlite":
        with op.batch_alter_table("users", recreate="always") as batch_op:
            for column in columns:
                batch_op.add_column(column)
        return

    for column in columns:
        op.add_column("users", column)


def upgrade() -> None:
    _add_user_columns()


def _drop_user_columns() -> None:
    column_names = (
        "password_changed_at",
        "last_login_at",
        "locked_at",
        "failed_login_count",
    )

    if _dialect_name() == "sqlite" and _offline_mode():
        for column_name in column_names:
            op.drop_column("users", column_name)
        return

    if _dialect_name() == "sqlite":
        with op.batch_alter_table("users", recreate="always") as batch_op:
            for column_name in column_names:
                batch_op.drop_column(column_name)
        return

    for column_name in column_names:
        if column_name == "failed_login_count" and _dialect_name() == "mssql":
            op.drop_column("users", column_name, mssql_drop_default=True)
        else:
            op.drop_column("users", column_name)


def downgrade() -> None:
    _drop_user_columns()
