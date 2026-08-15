"""RBAC, account lifecycle, and authoritative module projection foundation."""

from typing import Sequence, Union

from alembic import context, op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c7e4a1b93d42"
down_revision: Union[str, Sequence[str], None] = "a4fcbd8f8388"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


USER_STATUS_VALUES = (
    "pending_approval",
    "active",
    "disabled",
    "locked",
    "rejected",
    "password_change_required",
)
BUSINESS_AREA_VALUES = ("crew", "maintenance", "stores", "admin")
MODULE_STATUS_VALUES = ("active", "frozen", "hidden")
APP_ROLE_VALUES = ("super_admin", "admin", "engineer", "viewer", "guest")


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


def _check(column: str, values: Sequence[str], name: str) -> sa.CheckConstraint:
    quoted_values = ", ".join(f"'{value}'" for value in values)
    return sa.CheckConstraint(f"{column} IN ({quoted_values})", name=name)


def _emit_offline_check(table: str, column: str, values: Sequence[str], name: str) -> None:
    quoted_values = ", ".join(f"'{value}'" for value in values)
    op.execute(
        f"ALTER TABLE {table} ADD CONSTRAINT {name} CHECK ({column} IN ({quoted_values}))"
    )


def _add_module_columns() -> None:
    columns = (
        sa.Column(
            "business_area",
            _enum_type(BUSINESS_AREA_VALUES, "ck_modules_business_area"),
            nullable=True,
        ),
        sa.Column("route", sa.String(length=255), nullable=True),
        sa.Column(
            "module_status",
            _enum_type(MODULE_STATUS_VALUES, "ck_modules_module_status"),
            nullable=True,
        ),
        sa.Column("required_view_permission", sa.String(length=128), nullable=True),
        sa.Column("display_name_key", sa.String(length=128), nullable=True),
        sa.Column("action_permissions", sa.JSON(), nullable=True),
    )

    if _dialect_name() == "sqlite" and _offline_mode():
        for column in columns:
            op.add_column("modules", column)
        _emit_offline_check("modules", "business_area", BUSINESS_AREA_VALUES, "ck_modules_business_area")
        _emit_offline_check("modules", "module_status", MODULE_STATUS_VALUES, "ck_modules_module_status")
        return

    if _dialect_name() == "sqlite":
        with op.batch_alter_table("modules", recreate="always") as batch_op:
            for column in columns:
                batch_op.add_column(column)
            batch_op.create_check_constraint(
                "ck_modules_business_area",
                "business_area IN ('crew', 'maintenance', 'stores', 'admin')",
            )
            batch_op.create_check_constraint(
                "ck_modules_module_status",
                "module_status IN ('active', 'frozen', 'hidden')",
            )
        return

    for column in columns:
        op.add_column("modules", column)
    op.create_check_constraint(
        "ck_modules_business_area",
        "modules",
        "business_area IN ('crew', 'maintenance', 'stores', 'admin')",
    )
    op.create_check_constraint(
        "ck_modules_module_status",
        "modules",
        "module_status IN ('active', 'frozen', 'hidden')",
    )


def _convert_user_status() -> None:
    allowed = ", ".join(f"'{value}'" for value in USER_STATUS_VALUES)
    op.execute(
        sa.text(
            "UPDATE users "
            "SET status = 'active' "
            f"WHERE status IS NULL OR status NOT IN ({allowed})"
        )
    )

    status_type = _enum_type(USER_STATUS_VALUES, "ck_users_status")
    if _dialect_name() == "sqlite" and _offline_mode():
        op.alter_column(
            "users",
            "status",
            existing_type=sa.String(length=32),
            type_=status_type,
            existing_nullable=True,
        )
        _emit_offline_check("users", "status", USER_STATUS_VALUES, "ck_users_status")
        return

    if _dialect_name() == "sqlite":
        with op.batch_alter_table("users", recreate="always") as batch_op:
            batch_op.alter_column(
                "status",
                existing_type=sa.String(length=32),
                type_=status_type,
                existing_nullable=True,
            )
            batch_op.create_check_constraint(
                "ck_users_status",
                "status IN ('pending_approval', 'active', 'disabled', 'locked', 'rejected', 'password_change_required')",
            )
        return

    op.alter_column(
        "users",
        "status",
        existing_type=sa.String(length=32),
        type_=status_type,
        existing_nullable=True,
    )
    op.create_check_constraint(
        "ck_users_status",
        "users",
        "status IN ('pending_approval', 'active', 'disabled', 'locked', 'rejected', 'password_change_required')",
    )


def upgrade() -> None:
    op.create_table(
        "permissions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("key", sa.String(length=128), nullable=False),
        sa.Column("description", sa.Unicode(length=1024), nullable=True),
        sa.Column(
            "business_area",
            _enum_type(BUSINESS_AREA_VALUES, "ck_permissions_business_area"),
            nullable=True,
        ),
        _check("business_area", BUSINESS_AREA_VALUES, "ck_permissions_business_area"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_permissions")),
    )
    op.create_index(op.f("ix_permissions_key"), "permissions", ["key"], unique=True)

    op.create_table(
        "role_permissions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column(
            "role",
            _enum_type(APP_ROLE_VALUES, "ck_role_permissions_role"),
            nullable=False,
        ),
        sa.Column("permission_key", sa.String(length=128), nullable=False),
        _check("role", APP_ROLE_VALUES, "ck_role_permissions_role"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_role_permissions")),
        sa.UniqueConstraint(
            "role",
            "permission_key",
            name=op.f("uq_role_permissions_role"),
        ),
    )
    op.create_index(
        op.f("ix_role_permissions_permission_key"),
        "role_permissions",
        ["permission_key"],
        unique=False,
    )

    _add_module_columns()
    _convert_user_status()


def _drop_module_columns() -> None:
    column_names = (
        "action_permissions",
        "display_name_key",
        "required_view_permission",
        "module_status",
        "route",
        "business_area",
    )
    if _dialect_name() == "sqlite" and _offline_mode():
        op.execute("ALTER TABLE modules DROP CONSTRAINT ck_modules_business_area")
        op.execute("ALTER TABLE modules DROP CONSTRAINT ck_modules_module_status")
        for column_name in column_names:
            op.drop_column("modules", column_name)
        return

    if _dialect_name() == "sqlite":
        with op.batch_alter_table("modules", recreate="always") as batch_op:
            batch_op.drop_constraint("ck_modules_business_area", type_="check")
            batch_op.drop_constraint("ck_modules_module_status", type_="check")
            for column_name in column_names:
                batch_op.drop_column(column_name)
        return

    op.drop_constraint("ck_modules_business_area", "modules", type_="check")
    op.drop_constraint("ck_modules_module_status", "modules", type_="check")
    for column_name in column_names:
        op.drop_column("modules", column_name)


def _revert_user_status() -> None:
    if _dialect_name() == "sqlite" and _offline_mode():
        op.execute("ALTER TABLE users DROP CONSTRAINT ck_users_status")
        op.alter_column(
            "users",
            "status",
            existing_type=sa.String(length=24),
            type_=sa.String(length=32),
            existing_nullable=True,
        )
        return

    if _dialect_name() == "sqlite":
        with op.batch_alter_table("users", recreate="always") as batch_op:
            batch_op.drop_constraint("ck_users_status", type_="check")
            batch_op.alter_column(
                "status",
                existing_type=sa.String(length=24),
                type_=sa.String(length=32),
                existing_nullable=True,
            )
        return

    op.drop_constraint("ck_users_status", "users", type_="check")
    op.alter_column(
        "users",
        "status",
        existing_type=sa.String(length=24),
        type_=sa.String(length=32),
        existing_nullable=True,
    )


def downgrade() -> None:
    _drop_module_columns()
    _revert_user_status()

    op.drop_index(op.f("ix_role_permissions_permission_key"), table_name="role_permissions")
    op.drop_table("role_permissions")
    op.drop_index(op.f("ix_permissions_key"), table_name="permissions")
    op.drop_table("permissions")
