"""Synchronize the code-owned RBAC and module registry into the database."""

from __future__ import annotations

import sys

from sqlalchemy.orm import Session

from backend.database import SessionLocal
from backend.models import AppRole, Module, Permission, RolePermission
from backend.rbac.registry import (
    MODULE_REGISTRY,
    PERMISSION_CATALOGUE,
    expected_role_permissions,
)


def sync_registry(db: Session | None = None) -> dict[str, int]:
    """Idempotently project modules, permissions, and role defaults into SQL."""

    owns_session = db is None
    session = db or SessionLocal()
    try:
        for definition in MODULE_REGISTRY:
            module = session.query(Module).filter(Module.key == definition.key).first()
            if module is None:
                module = Module(key=definition.key, enabled=True)
                session.add(module)

            module.name = definition.name
            module.description = definition.description
            module.icon = definition.icon
            module.category = definition.category
            module.business_area = definition.business_area
            module.route = definition.route
            module.module_status = definition.module_status
            module.required_view_permission = definition.required_view_permission
            module.display_name_key = definition.display_name_key
            module.action_permissions = list(definition.action_permissions)
            module.sort_order = definition.sort_order

        for definition in PERMISSION_CATALOGUE:
            permission = session.query(Permission).filter(Permission.key == definition.key).first()
            if permission is None:
                permission = Permission(key=definition.key)
                session.add(permission)
            permission.description = definition.description
            permission.business_area = definition.business_area

        session.flush()

        permission_keys = {
            permission.key for permission in session.query(Permission).all() if permission.key
        }
        expected = expected_role_permissions(permission_keys)

        for role in AppRole:
            desired = expected[role]
            current_rows = session.query(RolePermission).filter(RolePermission.role == role).all()
            current_by_key = {row.permission_key: row for row in current_rows}

            for row in current_rows:
                if row.permission_key not in desired:
                    session.delete(row)

            for permission_key in desired - set(current_by_key):
                session.add(RolePermission(role=role, permission_key=permission_key))

        session.commit()
        return {
            "modules": session.query(Module).count(),
            "permissions": session.query(Permission).count(),
            "role_permissions": session.query(RolePermission).count(),
        }
    except Exception:
        session.rollback()
        raise
    finally:
        if owns_session:
            session.close()


def main() -> int:
    try:
        counts = sync_registry()
    except Exception as exc:
        print(f"Registry sync failed: {type(exc).__name__}", file=sys.stderr)
        return 1

    print(
        "Registry sync complete: "
        f"{counts['modules']} modules, "
        f"{counts['permissions']} permissions, "
        f"{counts['role_permissions']} role permissions."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
