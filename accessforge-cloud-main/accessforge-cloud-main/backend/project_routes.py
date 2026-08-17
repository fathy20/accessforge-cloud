from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional
from pydantic import BaseModel, Field

from .database import get_db
from .models import AppRole, User, Project
from .auth import get_current_user
from .rbac.permissions import record_audit

router = APIRouter(prefix="/api/projects", tags=["projects"])

class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    code: Optional[str] = Field(default=None, max_length=64)
    description: Optional[str] = Field(default=None, max_length=4000)
    # The UI has always submitted these; they were silently dropped before the
    # columns existed.
    tail_number: Optional[str] = Field(default=None, max_length=64)
    station: Optional[str] = Field(default=None, max_length=64)


def _project_payload(project: Project) -> dict:
    return {
        "id": project.id,
        "owner_id": project.owner_id,
        "name": project.name,
        "code": project.code,
        "tail_number": project.tail_number,
        "station": project.station,
        "description": project.description,
        "status": project.status,
        "created_at": project.created_at,
    }

@router.get("")
def list_projects(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    # Projects are shared workspaces (the UI badges "mine" vs others), so every
    # authenticated user sees the list — but bounded and newest first.
    projects = (
        db.query(Project)
        .order_by(Project.created_at.desc())
        .limit(200)
        .all()
    )
    return [_project_payload(p) for p in projects]

@router.post("")
def create_project(payload: ProjectCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    proj = Project(
        owner_id=current_user.id,
        name=payload.name,
        code=payload.code,
        tail_number=payload.tail_number,
        station=payload.station,
        description=payload.description
    )
    db.add(proj)
    db.commit()
    db.refresh(proj)
    return _project_payload(proj)


def _is_admin(user: User) -> bool:
    return any(role.role in (AppRole.admin, AppRole.super_admin) for role in user.roles)


@router.delete("/{project_id}")
def delete_project(
    project_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # The UI offers deletion to the owner and to admins; the server enforces it.
    proj = db.query(Project).filter(Project.id == project_id).first()
    if proj is None:
        raise HTTPException(status_code=404, detail="Project not found")
    if proj.owner_id != current_user.id and not _is_admin(current_user):
        raise HTTPException(status_code=403, detail="Only the owner or an admin can delete a project")

    db.delete(proj)
    record_audit(db, current_user, "delete", "project", proj.id, name=proj.name)
    db.commit()
    return {"status": "success"}
