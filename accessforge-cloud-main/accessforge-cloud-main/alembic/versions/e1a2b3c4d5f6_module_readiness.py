"""Persist informational module readiness state."""

from typing import Sequence, Union

from alembic import context, op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "e1a2b3c4d5f6"
down_revision: Union[str, Sequence[str], None] = "d9f0a2b7c4e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


MODULE_READINESS_VALUES = (
    "available",
    "pilot",
    "under_validation",
    "requires_configuration",
    "under_development",
    "not_migrated",
    "discovery_required",
)


def _dialect_name() -> str:
    return op.get_bind().dialect.name


def _offline_mode() -> bool:
    return context.is_offline_mode()


def _enum_type(values: Sequence[str], name: str) -> sa.Enum:
    return sa.Enum(
        *values,
        native_enum=False,
        create_constraint=False,
        name=name,
    )


def _emit_offline_check(table: str, column: str, values: Sequence[str], name: str) -> None:
    quoted_values = ", ".join(f"'{value}'" for value in values)
    op.execute(
        f"ALTER TABLE {table} ADD CONSTRAINT {name} CHECK ({column} IN ({quoted_values}))"
    )


def _backfill_readiness() -> None:
    op.execute(sa.text("UPDATE modules SET readiness = 'under_development'"))


def _add_module_readiness() -> None:
    column = sa.Column(
        "readiness",
        _enum_type(MODULE_READINESS_VALUES, "ck_modules_readiness"),
        nullable=True,
    )

    if _dialect_name() == "sqlite" and _offline_mode():
        op.add_column("modules", column)
        _emit_offline_check(
            "modules",
            "readiness",
            MODULE_READINESS_VALUES,
            "ck_modules_readiness",
        )
        _backfill_readiness()
        return

    if _dialect_name() == "sqlite":
        with op.batch_alter_table("modules", recreate="always") as batch_op:
            batch_op.add_column(column)
            batch_op.create_check_constraint(
                "ck_modules_readiness",
                "readiness IN ('available', 'pilot', 'under_validation', 'requires_configuration', 'under_development', 'not_migrated', 'discovery_required')",
            )
        _backfill_readiness()
        return

    op.add_column("modules", column)
    op.create_check_constraint(
        "ck_modules_readiness",
        "modules",
        "readiness IN ('available', 'pilot', 'under_validation', 'requires_configuration', 'under_development', 'not_migrated', 'discovery_required')",
    )
    _backfill_readiness()


def upgrade() -> None:
    _add_module_readiness()


def _drop_module_readiness() -> None:
    if _dialect_name() == "sqlite" and _offline_mode():
        op.execute("ALTER TABLE modules DROP CONSTRAINT ck_modules_readiness")
        op.drop_column("modules", "readiness")
        return

    if _dialect_name() == "sqlite":
        with op.batch_alter_table("modules", recreate="always") as batch_op:
            batch_op.drop_constraint("ck_modules_readiness", type_="check")
            batch_op.drop_column("readiness")
        return

    op.drop_constraint("ck_modules_readiness", "modules", type_="check")
    op.drop_column("modules", "readiness")


def downgrade() -> None:
    _drop_module_readiness()
