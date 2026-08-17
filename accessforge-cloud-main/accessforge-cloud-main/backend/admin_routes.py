import uuid
from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .auth import generate_temporary_password, reset_login_rate_limit
from .database import get_db
from .models import (
    AppRole,
    AuditLog,
    Module,
    Permission,
    User,
    UserInvitation,
    UserRole,
    UserStatus,
)
from .rbac.permissions import (
    get_effective_permissions,
    has_permission,
    record_audit,
    require_permission,
)


router = APIRouter(prefix="/api/admin", tags=["admin"])


class StatusUpdate(BaseModel):
    status: str


class RoleUpdate(BaseModel):
    roles: List[str]


class ApprovalRequest(BaseModel):
    roles: List[str]


class AdminUserCreate(BaseModel):
    email: str
    full_name: str | None = None
    roles: List[str]


class InvitationCreate(BaseModel):
    email: str
    role: str


def _enum_value(value):
    return value.value if hasattr(value, "value") else value


def _role_values(user: User) -> list[str]:
    return [str(_enum_value(role.role)) for role in user.roles]


def _has_super_admin_role(user: User) -> bool:
    return any(role.role == AppRole.super_admin for role in user.roles)


def _parse_roles(role_values: List[str]) -> list[AppRole]:
    parsed: list[AppRole] = []
    invalid: list[str] = []
    for role_value in role_values:
        try:
            role = AppRole(role_value)
        except ValueError:
            invalid.append(role_value)
            continue
        if role not in parsed:
            parsed.append(role)
    if invalid:
        raise HTTPException(status_code=400, detail=f"Unknown role: {invalid[0]}")
    return parsed


def _require_super_admin_role_permission(
    db: Session,
    current_user: User,
    old_roles: set[AppRole],
    new_roles: set[AppRole],
) -> None:
    role_changed = (AppRole.super_admin in old_roles) != (AppRole.super_admin in new_roles)
    if role_changed and not has_permission(
        db,
        current_user,
        "admin.roles.manage_super_admin",
    ):
        raise HTTPException(
            status_code=403,
            detail="Super-admin role changes require the admin.roles.manage_super_admin permission",
        )


def _module_payload(module: Module, *, include_id: bool = True) -> dict:
    payload = {
        "key": module.key,
        "name": module.name,
        "description": module.description,
        "icon": module.icon,
        "category": module.category,
        "enabled": bool(module.enabled),
        "sort_order": module.sort_order,
        "business_area": _enum_value(module.business_area),
        "route": module.route,
        "module_status": _enum_value(module.module_status),
        "readiness": _enum_value(module.readiness),
        "required_view_permission": module.required_view_permission,
        "display_name_key": module.display_name_key,
        "action_permissions": list(module.action_permissions or []),
    }
    if include_id:
        payload["id"] = module.id
    return payload


@router.get("/users")
def list_users(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("admin.users.view")),
):
    users = db.query(User).all()
    result = []
    for user in users:
        result.append(
            {
                "id": user.id,
                "email": user.email,
                "full_name": user.full_name,
                "department": user.department,
                "job_title": user.job_title,
                "phone": user.phone,
                "employee_id": user.employee_id,
                "status": _enum_value(user.status),
                "roles": _role_values(user),
                "created_at": user.created_at,
            }
        )
    return result


@router.post("/users/{user_id}/status")
def update_user_status(
    user_id: str,
    payload: StatusUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("admin.users.manage")),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    try:
        new_status = UserStatus(payload.status)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid user status") from None

    if current_user.id == user.id and new_status in {
        UserStatus.disabled,
        UserStatus.locked,
        UserStatus.rejected,
    }:
        raise HTTPException(status_code=409, detail="You cannot disable or reject your own account")

    target_has_super_admin = _has_super_admin_role(user)
    if target_has_super_admin and new_status != UserStatus.active:
        active_super_admins = (
            db.query(User.id)
            .select_from(User)
            .join(UserRole, User.id == UserRole.user_id)
            .filter(
                UserRole.role == AppRole.super_admin,
                User.status == UserStatus.active,
                User.id != user.id,
            )
            .distinct()
            .count()
        )
        if active_super_admins == 0:
            raise HTTPException(status_code=409, detail="The last active super-admin cannot be deactivated")

    old_status = user.status
    if old_status != new_status:
        user.status = new_status
        if new_status == UserStatus.active:
            action = "enable"
        elif new_status == UserStatus.disabled:
            action = "disable"
        else:
            action = "status_change"
        record_audit(
            db,
            current_user,
            action,
            "user",
            user.id,
            old_status=old_status,
            new_status=new_status,
        )
        db.commit()

    return {
        "status": "success",
        "user_id": user_id,
        "new_status": _enum_value(user.status),
    }


@router.post("/users/{user_id}/roles")
def update_user_roles(
    user_id: str,
    payload: RoleUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("admin.roles.manage")),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    new_roles = _parse_roles(payload.roles)
    old_roles = {role.role for role in user.roles}
    new_role_set = set(new_roles)
    _require_super_admin_role_permission(db, current_user, old_roles, new_role_set)
    removes_super_admin = AppRole.super_admin in old_roles and AppRole.super_admin not in new_role_set

    if removes_super_admin and current_user.id == user.id:
        raise HTTPException(status_code=409, detail="You cannot remove your own super-admin role")
    if removes_super_admin:
        super_admin_assignments = (
            db.query(UserRole).filter(UserRole.role == AppRole.super_admin).count()
        )
        target_super_admin_assignments = (
            db.query(UserRole)
            .filter(UserRole.user_id == user_id, UserRole.role == AppRole.super_admin)
            .count()
        )
        if super_admin_assignments - target_super_admin_assignments < 1:
            raise HTTPException(status_code=409, detail="The last super-admin role cannot be removed")

    added_roles = new_role_set - old_roles
    removed_roles = old_roles - new_role_set

    db.query(UserRole).filter(UserRole.user_id == user_id).delete(synchronize_session=False)
    for role in new_roles:
        db.add(UserRole(user_id=user_id, role=role))
    for role in sorted(added_roles, key=lambda value: value.value):
        record_audit(db, current_user, "role_assignment", "user", user.id, role=role)
    for role in sorted(removed_roles, key=lambda value: value.value):
        record_audit(db, current_user, "role_removal", "user", user.id, role=role)
    db.commit()
    return {"status": "success", "user_id": user_id, "roles": [role.value for role in new_roles]}


@router.post("/users/{user_id}/approve")
def approve_user(
    user_id: str,
    payload: ApprovalRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("admin.users.manage")),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.status != UserStatus.pending_approval:
        raise HTTPException(status_code=400, detail="User is not pending approval")
    if not payload.roles:
        raise HTTPException(status_code=400, detail="At least one role is required")

    new_roles = _parse_roles(payload.roles)
    if not new_roles:
        raise HTTPException(status_code=400, detail="At least one role is required")

    old_roles = {role.role for role in user.roles}
    _require_super_admin_role_permission(db, current_user, old_roles, set(new_roles))
    removes_super_admin = AppRole.super_admin in old_roles and AppRole.super_admin not in set(new_roles)
    if removes_super_admin:
        super_admin_assignments = (
            db.query(UserRole).filter(UserRole.role == AppRole.super_admin).count()
        )
        target_super_admin_assignments = (
            db.query(UserRole)
            .filter(UserRole.user_id == user_id, UserRole.role == AppRole.super_admin)
            .count()
        )
        if super_admin_assignments - target_super_admin_assignments < 1:
            raise HTTPException(status_code=409, detail="The last super-admin role cannot be removed")
    db.query(UserRole).filter(UserRole.user_id == user_id).delete(synchronize_session=False)
    for role in new_roles:
        db.add(UserRole(user_id=user_id, role=role))
        if role not in old_roles:
            record_audit(db, current_user, "role_assignment", "user", user.id, role=role)
    user.status = UserStatus.active
    record_audit(
        db,
        current_user,
        "approval",
        "user",
        user.id,
        roles=[role.value for role in new_roles],
    )
    db.commit()
    return {
        "status": "success",
        "user_id": user_id,
        "new_status": UserStatus.active.value,
        "roles": [role.value for role in new_roles],
    }


@router.post("/users", status_code=status.HTTP_201_CREATED)
def create_admin_user(
    payload: AdminUserCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("admin.users.manage")),
):
    if db.query(User).filter(User.email == payload.email).first():
        raise HTTPException(status_code=409, detail="Email already registered")
    if not payload.roles:
        raise HTTPException(status_code=400, detail="At least one role is required")

    new_roles = _parse_roles(payload.roles)
    if not new_roles:
        raise HTTPException(status_code=400, detail="At least one role is required")
    _require_super_admin_role_permission(db, current_user, set(), set(new_roles))

    temporary_password, hashed_password = generate_temporary_password()
    user = User(
        email=payload.email,
        full_name=payload.full_name,
        hashed_password=hashed_password,
        status=UserStatus.password_change_required,
        password_changed_at=datetime.now(timezone.utc),
    )
    db.add(user)
    db.flush()
    for role in new_roles:
        db.add(UserRole(user_id=user.id, role=role))

    role_values = [role.value for role in new_roles]
    record_audit(
        db,
        current_user,
        "admin_user_creation",
        "user",
        user.id,
        email=user.email,
        roles=role_values,
    )
    for role in new_roles:
        record_audit(db, current_user, "role_assignment", "user", user.id, role=role)
    db.commit()
    return {
        "id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "status": _enum_value(user.status),
        "roles": role_values,
        "temporary_password": temporary_password,
    }


@router.post("/users/{user_id}/unlock")
def unlock_user(
    user_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("admin.users.manage")),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.status != UserStatus.locked:
        raise HTTPException(status_code=400, detail="User is not locked")

    user.status = UserStatus.active
    user.failed_login_count = 0
    user.locked_at = None
    record_audit(db, current_user, "account_unlock", "user", user.id)
    db.commit()
    reset_login_rate_limit(user.email)
    return {
        "status": "success",
        "user_id": user.id,
        "new_status": UserStatus.active.value,
    }


@router.post("/users/{user_id}/reset-password")
def reset_user_password(
    user_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("admin.users.manage")),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if _has_super_admin_role(user) and not has_permission(
        db,
        current_user,
        "admin.roles.manage_super_admin",
    ):
        raise HTTPException(
            status_code=403,
            detail="Resetting a super-admin password requires the admin.roles.manage_super_admin permission",
        )
    if user.status in {UserStatus.rejected, UserStatus.pending_approval}:
        raise HTTPException(status_code=400, detail="Password reset is not available for this account status")

    temporary_password, hashed_password = generate_temporary_password()
    user.hashed_password = hashed_password
    user.password_changed_at = datetime.now(timezone.utc)
    user.failed_login_count = 0
    user.locked_at = None
    user.status = UserStatus.password_change_required
    record_audit(
        db,
        current_user,
        "password_reset",
        "user",
        user.id,
        target_status=UserStatus.password_change_required,
    )
    db.commit()
    reset_login_rate_limit(user.email)
    return {
        "status": "success",
        "user_id": user.id,
        "temporary_password": temporary_password,
    }


@router.post("/users/{user_id}/reject")
def reject_user(
    user_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("admin.users.manage")),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.status != UserStatus.pending_approval:
        raise HTTPException(status_code=400, detail="User is not pending approval")

    user.status = UserStatus.rejected
    record_audit(db, current_user, "rejection", "user", user.id)
    db.commit()
    return {"status": "success", "user_id": user_id, "new_status": UserStatus.rejected.value}


@router.get("/permissions")
def list_permissions(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("admin.roles.manage")),
):
    permissions = db.query(Permission).order_by(Permission.key).all()
    return [
        {
            "key": permission.key,
            "description": permission.description,
            "business_area": _enum_value(permission.business_area),
        }
        for permission in permissions
    ]


@router.get("/users/{user_id}/effective-permissions")
def list_effective_permissions(
    user_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("admin.users.view")),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return {"user_id": user.id, "permissions": sorted(get_effective_permissions(db, user))}


@router.get("/invitations")
def list_invitations(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("admin.users.manage")),
):
    invitations = db.query(UserInvitation).all()
    return [
        {
            "id": invitation.id,
            "email": invitation.email,
            "role": invitation.role,
            "token": invitation.token,
            "accepted_at": invitation.accepted_at,
            "created_at": invitation.created_at,
        }
        for invitation in invitations
    ]


@router.post("/invitations")
def create_invitation(
    payload: InvitationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("admin.users.manage")),
):
    invitation = UserInvitation(
        email=payload.email,
        role=payload.role,
        token=str(uuid.uuid4()),
        invited_by=current_user.id,
    )
    db.add(invitation)
    db.flush()
    record_audit(
        db,
        current_user,
        "admin_user_creation",
        "user_invitation",
        invitation.id,
        email=payload.email,
        role=payload.role,
    )
    db.commit()
    db.refresh(invitation)
    return {
        "id": invitation.id,
        "email": invitation.email,
        "role": invitation.role,
        "token": invitation.token,
        "created_at": invitation.created_at,
    }


@router.delete("/invitations/{invitation_id}")
def revoke_invitation(
    invitation_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("admin.users.manage")),
):
    db.query(UserInvitation).filter(UserInvitation.id == invitation_id).delete()
    db.commit()
    return {"status": "success"}


@router.get("/audit")
def list_audit_logs(
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("admin.audit.view")),
):
    logs = db.query(AuditLog).order_by(AuditLog.ts.desc()).limit(limit).all()
    return [
        {
            "id": log.id,
            "actor_name": log.actor_name,
            "action": log.action,
            "entity": log.entity,
            "entity_id": log.entity_id,
            "metadata_json": log.metadata_json,
            "ts": log.ts,
        }
        for log in logs
    ]


@router.get("/modules")
def list_admin_modules(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("admin.modules.manage")),
):
    modules = db.query(Module).order_by(Module.sort_order, Module.key).all()
    return [_module_payload(module) for module in modules]
