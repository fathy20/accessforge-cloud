"""Authoritative role, permission, and module registry support."""

from .registry import (
    ADMIN_PERMISSION_KEYS,
    MODULE_REGISTRY,
    PERMISSION_CATALOGUE,
    ROLE_PERMISSION_DEFAULTS,
)
from .permissions import (
    get_effective_permissions,
    has_permission,
    record_audit,
    require_permission,
)

__all__ = [
    "ADMIN_PERMISSION_KEYS",
    "MODULE_REGISTRY",
    "PERMISSION_CATALOGUE",
    "ROLE_PERMISSION_DEFAULTS",
    "get_effective_permissions",
    "has_permission",
    "record_audit",
    "require_permission",
]
