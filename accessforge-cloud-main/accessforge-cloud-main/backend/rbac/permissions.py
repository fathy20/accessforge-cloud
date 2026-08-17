"""Permission checks, explicit FastAPI dependencies, and audit recording."""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Any, Callable, Mapping

from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import AuditLog, RolePermission, User, UserRole


def _user_id(user: User | str) -> str:
    return str(user.id if isinstance(user, User) else user)


def get_effective_permissions(db: Session, user: User | str) -> set[str]:
    """Return the union of explicit grants attached to the user's roles."""

    rows = (
        db.query(RolePermission.permission_key)
        .join(UserRole, RolePermission.role == UserRole.role)
        .filter(UserRole.user_id == _user_id(user))
        .all()
    )
    return {permission_key for (permission_key,) in rows if permission_key}


def has_permission(db: Session, user: User | str, permission_key: str | None) -> bool:
    """Check one permission with default-deny semantics."""

    if not permission_key:
        return False
    return permission_key in get_effective_permissions(db, user)


def require_permissions(*permission_keys: str) -> Callable[..., User]:
    """Build a FastAPI dependency that requires every listed grant.

    Every key must be held; a single missing grant is a 403 with the same body
    as any other denial, so a caller cannot probe which permission it lacks.
    """

    if not permission_keys:
        raise ValueError("require_permissions needs at least one permission key")

    # Keep auth and RBAC imports acyclic: auth records audit events from this
    # module, while the dependency needs auth only after both modules load.
    from ..auth import get_current_user

    def dependency(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> User:
        held = get_effective_permissions(db, current_user)
        if not all(key and key in held for key in permission_keys):
            raise HTTPException(status_code=403, detail="Permission denied")
        return current_user

    dependency.__name__ = "require_" + "_and_".join(
        key.replace(".", "_") for key in permission_keys
    )
    return dependency


def require_permission(permission_key: str) -> Callable[..., User]:
    """Build a FastAPI dependency that turns a missing explicit grant into 403."""

    return require_permissions(permission_key)


_SENSITIVE_METADATA_PARTS = ("password", "passwd", "hash", "token", "secret")


def _sensitive_key(key: object) -> bool:
    normalized = str(key).casefold()
    return any(part in normalized for part in _SENSITIVE_METADATA_PARTS)


def _safe_metadata(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _safe_metadata(item)
            for key, item in value.items()
            if not _sensitive_key(key)
        }
    if isinstance(value, (list, tuple, set)):
        return [_safe_metadata(item) for item in value]
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def record_audit(
    db: Session,
    actor: User | None,
    action: str,
    entity: str | None,
    entity_id: str | None,
    **metadata: Any,
) -> AuditLog:
    """Stage a sanitized audit row; the caller owns the surrounding commit."""

    actor_id = str(actor.id) if actor is not None else None
    actor_name = None
    if actor is not None:
        actor_name = actor.full_name or actor.email

    audit = AuditLog(
        user_id=actor_id,
        actor_name=actor_name,
        action=action,
        entity=entity,
        entity_id=str(entity_id) if entity_id is not None else None,
        metadata_json=_safe_metadata(metadata),
    )
    db.add(audit)
    return audit
