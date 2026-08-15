"""Persist secure upload artifact metadata and quarantine state."""

from typing import Sequence, Union

from alembic import context, op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f7a8b9c0d1e2"
down_revision: Union[str, Sequence[str], None] = "e1a2b3c4d5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


UPLOAD_SCAN_STATE_VALUES = (
    "not_scanned",
    "pending",
    "clean",
    "infected",
)


def _dialect_name() -> str:
    return op.get_bind().dialect.name


def _offline_mode() -> bool:
    return context.is_offline_mode()


def _scan_state_check() -> str:
    quoted_values = ", ".join(f"'{value}'" for value in UPLOAD_SCAN_STATE_VALUES)
    return f"scan_state IN ({quoted_values})"


def _emit_offline_check(table: str, column: str, values: Sequence[str], name: str) -> None:
    quoted_values = ", ".join(f"'{value}'" for value in values)
    op.execute(
        f"ALTER TABLE {table} ADD CONSTRAINT {name} CHECK ({column} IN ({quoted_values}))"
    )


def _upload_columns() -> tuple[sa.Column, ...]:
    return (
        sa.Column("sha256", sa.String(length=64), nullable=True),
        sa.Column(
            "scan_state",
            sa.String(length=16),
            nullable=False,
            server_default=sa.text("'not_scanned'"),
        ),
        sa.Column("retention_expires_at", sa.DateTime(timezone=True), nullable=True),
    )


def _add_upload_security_fields() -> None:
    columns = _upload_columns()

    if _dialect_name() == "sqlite" and _offline_mode():
        for column in columns:
            op.add_column("uploads", column)
        _emit_offline_check(
            "uploads",
            "scan_state",
            UPLOAD_SCAN_STATE_VALUES,
            "ck_uploads_scan_state",
        )
        op.create_index("ix_uploads_sha256", "uploads", ["sha256"], unique=False)
        return

    if _dialect_name() == "sqlite":
        with op.batch_alter_table("uploads", recreate="always") as batch_op:
            for column in columns:
                batch_op.add_column(column)
            batch_op.create_check_constraint(
                "ck_uploads_scan_state",
                _scan_state_check(),
            )
            batch_op.create_index("ix_uploads_sha256", ["sha256"], unique=False)
        return

    for column in columns:
        op.add_column("uploads", column)
    op.create_check_constraint(
        "ck_uploads_scan_state",
        "uploads",
        _scan_state_check(),
    )
    op.create_index("ix_uploads_sha256", "uploads", ["sha256"], unique=False)


def upgrade() -> None:
    _add_upload_security_fields()


def _drop_upload_security_fields() -> None:
    column_names = (
        "retention_expires_at",
        "scan_state",
        "sha256",
    )

    if _dialect_name() == "sqlite" and _offline_mode():
        op.drop_index("ix_uploads_sha256", table_name="uploads")
        op.execute("ALTER TABLE uploads DROP CONSTRAINT ck_uploads_scan_state")
        for column_name in column_names:
            op.drop_column("uploads", column_name)
        return

    if _dialect_name() == "sqlite":
        with op.batch_alter_table("uploads", recreate="always") as batch_op:
            batch_op.drop_index("ix_uploads_sha256")
            batch_op.drop_constraint("ck_uploads_scan_state", type_="check")
            for column_name in column_names:
                batch_op.drop_column(column_name)
        return

    op.drop_index("ix_uploads_sha256", table_name="uploads")
    op.drop_constraint("ck_uploads_scan_state", "uploads", type_="check")
    for column_name in column_names:
        if column_name == "scan_state" and _dialect_name() == "mssql":
            op.drop_column("uploads", column_name, mssql_drop_default=True)
        else:
            op.drop_column("uploads", column_name)


def downgrade() -> None:
    _drop_upload_security_fields()
