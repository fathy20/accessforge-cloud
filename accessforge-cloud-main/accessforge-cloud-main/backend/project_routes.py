from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel

from .database import get_db
from .models import User, Project
from .auth import get_current_user

router = APIRouter(prefix="/api/projects", tags=["projects"])

class ProjectCreate(BaseModel):
    name: str
    code: Optional[str] = None
    description: Optional[str] = None

@router.get("")
def list_projects(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    projects = db.query(Project).all()
    return [{
        "id": p.id,
        "owner_id": p.owner_id,
        "name": p.name,
        "code": p.code,
        "description": p.description,
        "status": p.status,
        "created_at": p.created_at
    } for p in projects]

@router.post("")
def create_project(payload: ProjectCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    proj = Project(
        owner_id=current_user.id,
        name=payload.name,
        code=payload.code,
        description=payload.description
    )
    db.add(proj)
    db.commit()
    db.refresh(proj)
    return {
        "id": proj.id,
        "owner_id": proj.owner_id,
        "name": proj.name,
        "code": proj.code,
        "description": proj.description,
        "status": proj.status,
        "created_at": proj.created_at
    }
