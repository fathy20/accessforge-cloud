"""Whether a module is visible to a user: the one rule the API and the job
runner both apply, kept out of main.py so the worker can import it without
loading the FastAPI application."""

from __future__ import annotations

from sqlalchemy.orm import Session

from .models import Module, ModuleAccess, ModuleStatus, User
from .rbac.permissions import get_effective_permissions
from .rbac.registry import MODULE_REGISTRY


def module_visibility_inputs(db: Session, user: User) -> tuple[set[str], set[str]]:
    permissions = get_effective_permissions(db, user)
    disabled_module_ids = {
        module_id
        for (module_id,) in db.query(ModuleAccess.module_id)
        .filter(ModuleAccess.user_id == user.id, ModuleAccess.enabled == False)  # noqa: E712
        .all()
    }
    return permissions, disabled_module_ids


def module_is_visible(
    module: Module | None,
    permissions: set[str],
    disabled_module_ids: set[str],
) -> bool:
    if module is None:
        return False

    registry_definition = next(
        (definition for definition in MODULE_REGISTRY if definition.key == module.key),
        None,
    )
    return (
        registry_definition is not None
        and module.required_view_permission == registry_definition.required_view_permission
        and bool(module.enabled)
        and module.module_status != ModuleStatus.hidden
        and module.id not in disabled_module_ids
        and bool(module.required_view_permission)
        and registry_definition.required_view_permission in permissions
    )
