from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime, timezone
import uuid

from .database import get_db
from .models import User, UserRole, AppRole, UserInvitation, AuditLog, Module, ModuleAccess
from .auth import get_current_user

router = APIRouter(prefix="/api/admin", tags=["admin"])

def check_admin(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    user_roles = [r.role for r in current_user.roles]
    if AppRole.super_admin not in user_roles and AppRole.admin not in user_roles:
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user

class StatusUpdate(BaseModel):
    status: str

class RoleUpdate(BaseModel):
    roles: List[str]

class InvitationCreate(BaseModel):
    email: str
    role: str

@router.get("/users")
def list_users(db: Session = Depends(get_db), current_user: User = Depends(check_admin)):
    users = db.query(User).all()
    result = []
    for u in users:
        roles = [r.role.value for r in u.roles]
        result.append({
            "id": u.id,
            "email": u.email,
            "full_name": u.full_name,
            "department": u.department,
            "job_title": u.job_title,
            "phone": u.phone,
            "employee_id": u.employee_id,
            "status": u.status,
            "roles": roles,
            "created_at": u.created_at
        })
    return result

@router.post("/users/{user_id}/status")
def update_user_status(user_id: str, payload: StatusUpdate, db: Session = Depends(get_db), current_user: User = Depends(check_admin)):
    u = db.query(User).filter(User.id == user_id).first()
    if not u:
        raise HTTPException(status_code=404, detail="User not found")
    u.status = payload.status
    db.commit()
    return {"status": "success", "user_id": user_id, "new_status": u.status}

@router.post("/users/{user_id}/roles")
def update_user_roles(user_id: str, payload: RoleUpdate, db: Session = Depends(get_db), current_user: User = Depends(check_admin)):
    u = db.query(User).filter(User.id == user_id).first()
    if not u:
        raise HTTPException(status_code=404, detail="User not found")
    # clear current roles
    db.query(UserRole).filter(UserRole.user_id == user_id).delete()
    for r_str in payload.roles:
        try:
            r_enum = AppRole(r_str)
            db.add(UserRole(user_id=user_id, role=r_enum))
        except ValueError:
            pass
    db.commit()
    return {"status": "success"}

@router.get("/invitations")
def list_invitations(db: Session = Depends(get_db), current_user: User = Depends(check_admin)):
    invs = db.query(UserInvitation).all()
    return [{
        "id": i.id,
        "email": i.email,
        "role": i.role,
        "token": i.token,
        "accepted_at": i.accepted_at,
        "created_at": i.created_at
    } for i in invs]

@router.post("/invitations")
def create_invitation(payload: InvitationCreate, db: Session = Depends(get_db), current_user: User = Depends(check_admin)):
    inv = UserInvitation(
        email=payload.email,
        role=payload.role,
        token=str(uuid.uuid4()),
        invited_by=current_user.id
    )
    db.add(inv)
    db.commit()
    db.refresh(inv)
    return {
        "id": inv.id,
        "email": inv.email,
        "role": inv.role,
        "token": inv.token,
        "created_at": inv.created_at
    }

@router.delete("/invitations/{invitation_id}")
def revoke_invitation(invitation_id: str, db: Session = Depends(get_db), current_user: User = Depends(check_admin)):
    db.query(UserInvitation).filter(UserInvitation.id == invitation_id).delete()
    db.commit()
    return {"status": "success"}

@router.get("/audit")
def list_audit_logs(limit: int = 100, db: Session = Depends(get_db), current_user: User = Depends(check_admin)):
    logs = db.query(AuditLog).order_by(AuditLog.ts.desc()).limit(limit).all()
    return [{
        "id": log.id,
        "actor_name": log.actor_name,
        "action": log.action,
        "entity": log.entity,
        "entity_id": log.entity_id,
        "metadata_json": log.metadata_json,
        "ts": log.ts
    } for log in logs]

@router.get("/modules")
def list_admin_modules(db: Session = Depends(get_db), current_user: User = Depends(check_admin)):
    return [
        {"id": "mod-1", "key": "task_extractor", "name": "Task Extractor", "category": "PDF Processing", "enabled": True},
        {"id": "mod-2", "key": "task_stamping", "name": "Task Stamping", "category": "PDF Processing", "enabled": True},
        {"id": "mod-3", "key": "effectivity", "name": "Effectivity / TCM", "category": "Aviation", "enabled": True},
        {"id": "mod-4", "key": "check_control", "name": "Check Control", "category": "Quality", "enabled": True},
        {"id": "mod-5", "key": "utilization", "name": "Utilization", "category": "Analytics", "enabled": True},
        {"id": "mod-6", "key": "cmp_tcm", "name": "CMP / TCM", "category": "Compliance", "enabled": True},
        {"id": "mod-7", "key": "cover_merge", "name": "Cover Merge", "category": "Documents", "enabled": True},
        {"id": "mod-8", "key": "mail_merge", "name": "Mail Merge", "category": "Documents", "enabled": True},
    ]
