"""The code-owned module and permission registry.

The database tables are projections of these definitions.  Runtime code should
import this module instead of maintaining a second list of modules or grants.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from ..models import AppRole, BusinessArea, ModuleStatus


@dataclass(frozen=True)
class ModuleDefinition:
    key: str
    name: str
    category: str
    business_area: BusinessArea
    module_status: ModuleStatus
    route: str
    required_view_permission: str
    display_name_key: str
    action_permissions: tuple[str, ...] = ()
    description: str | None = None
    icon: str | None = None
    sort_order: int = 0


def _module(
    key: str,
    name: str,
    category: str,
    business_area: BusinessArea,
    route: str,
    *,
    action_permissions: tuple[str, ...] = (),
    sort_order: int,
) -> ModuleDefinition:
    return ModuleDefinition(
        key=key,
        name=name,
        category=category,
        business_area=business_area,
        module_status=ModuleStatus.active,
        route=route,
        required_view_permission=f"{key}.view",
        display_name_key=f"modules.{key}.name",
        action_permissions=action_permissions,
        sort_order=sort_order,
    )


MODULE_REGISTRY: tuple[ModuleDefinition, ...] = (
    _module(
        "task_extractor",
        "Task Extractor",
        "PDF Processing",
        BusinessArea.maintenance,
        "/modules/task-extractor",
        sort_order=1,
    ),
    _module(
        "task_stamping",
        "Task Stamping",
        "PDF Processing",
        BusinessArea.maintenance,
        "/modules/task-stamping",
        sort_order=2,
    ),
    _module(
        "effectivity",
        "Effectivity / TCM",
        "Aviation",
        BusinessArea.maintenance,
        "/modules/effectivity",
        sort_order=3,
    ),
    _module(
        "check_control",
        "Check Control",
        "Quality",
        BusinessArea.maintenance,
        "/modules/check-control",
        action_permissions=("check_control.export",),
        sort_order=4,
    ),
    _module(
        "utilization",
        "Utilization",
        "Analytics",
        BusinessArea.maintenance,
        "/modules/utilization",
        action_permissions=("utilization.export",),
        sort_order=5,
    ),
    _module(
        "cmp_tcm",
        "CMP / TCM",
        "Compliance",
        BusinessArea.maintenance,
        "/modules/cmp-tcm",
        sort_order=6,
    ),
    _module(
        "cover_merge",
        "Cover Merge",
        "Documents",
        BusinessArea.maintenance,
        "/modules/cover-merge",
        sort_order=7,
    ),
    _module(
        "mail_merge",
        "Mail Merge",
        "Documents",
        BusinessArea.maintenance,
        "/modules/mail-merge",
        sort_order=8,
    ),
    _module(
        "crew_hours",
        "Crew Hours",
        "Statistics",
        BusinessArea.crew,
        "/modules/crew-hours",
        action_permissions=("crew_hours.export",),
        sort_order=9,
    ),
)

# A short alias keeps call sites readable while preserving one source of truth.
MODULES = MODULE_REGISTRY


@dataclass(frozen=True)
class PermissionDefinition:
    key: str
    description: str
    business_area: BusinessArea | None


def _module_permissions() -> tuple[PermissionDefinition, ...]:
    definitions: list[PermissionDefinition] = []
    for module in MODULE_REGISTRY:
        definitions.append(
            PermissionDefinition(
                key=module.required_view_permission,
                description=f"View the {module.name} module.",
                business_area=module.business_area,
            )
        )
        for action in module.action_permissions:
            definitions.append(
                PermissionDefinition(
                    key=action,
                    description=f"Use the {action.rsplit('.', 1)[-1]} action in the {module.name} module.",
                    business_area=module.business_area,
                )
            )
    return tuple(definitions)


ADMIN_PERMISSION_KEYS: tuple[str, ...] = (
    "admin.users.view",
    "admin.users.manage",
    "admin.roles.manage",
    "admin.roles.manage_super_admin",
    "admin.modules.manage",
    "admin.audit.view",
)

_ADMIN_PERMISSION_DEFINITIONS: tuple[PermissionDefinition, ...] = (
    PermissionDefinition("admin.users.view", "View user accounts.", BusinessArea.admin),
    PermissionDefinition("admin.users.manage", "Approve, reject, enable, or disable users.", BusinessArea.admin),
    PermissionDefinition("admin.roles.manage", "Assign and remove application roles.", BusinessArea.admin),
    PermissionDefinition(
        "admin.roles.manage_super_admin",
        "Grant or revoke the super-admin role.",
        BusinessArea.admin,
    ),
    PermissionDefinition("admin.modules.manage", "Manage the module registry projection.", BusinessArea.admin),
    PermissionDefinition("admin.audit.view", "View audit events.", BusinessArea.admin),
)

PERMISSION_CATALOGUE: tuple[PermissionDefinition, ...] = (
    *_module_permissions(),
    *_ADMIN_PERMISSION_DEFINITIONS,
)

PERMISSION_KEYS: tuple[str, ...] = tuple(item.key for item in PERMISSION_CATALOGUE)
MODULE_VIEW_PERMISSION_KEYS: frozenset[str] = frozenset(
    module.required_view_permission for module in MODULE_REGISTRY
)
MODULE_ACTION_PERMISSION_KEYS: frozenset[str] = frozenset(
    action for module in MODULE_REGISTRY for action in module.action_permissions
)
ALL_MODULE_PERMISSION_KEYS: frozenset[str] = frozenset(
    MODULE_VIEW_PERMISSION_KEYS | MODULE_ACTION_PERMISSION_KEYS
)

ROLE_PERMISSION_DEFAULTS: dict[AppRole, frozenset[str]] = {
    AppRole.super_admin: frozenset(PERMISSION_KEYS),
    AppRole.admin: frozenset(
        (set(ADMIN_PERMISSION_KEYS) - {"admin.roles.manage_super_admin"})
        | set(ALL_MODULE_PERMISSION_KEYS)
    ),
    AppRole.engineer: frozenset(ALL_MODULE_PERMISSION_KEYS),
    AppRole.viewer: MODULE_VIEW_PERMISSION_KEYS,
    AppRole.guest: frozenset(),
}


def expected_role_permissions(
    permission_keys: Iterable[str] | None = None,
) -> dict[AppRole, set[str]]:
    """Return a mutable copy of the defaults for a sync operation.

    ``super_admin`` is deliberately calculated from the permission rows that
    exist, so it remains an explicit grant for every catalogue entry.
    """

    existing_keys = set(PERMISSION_KEYS if permission_keys is None else permission_keys)
    defaults = {role: set(keys) for role, keys in ROLE_PERMISSION_DEFAULTS.items()}
    defaults[AppRole.super_admin] = existing_keys
    return defaults
