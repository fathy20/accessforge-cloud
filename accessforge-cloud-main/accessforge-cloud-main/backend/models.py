from sqlalchemy import Column, String, Boolean, Integer, DateTime, ForeignKey, Enum, JSON
from sqlalchemy.orm import relationship
import enum
import uuid
from datetime import datetime, timezone

from .database import Base

def gen_uuid():
    return str(uuid.uuid4())

class AppRole(str, enum.Enum):
    super_admin = "super_admin"
    admin = "admin"
    engineer = "engineer"
    viewer = "viewer"
    guest = "guest"

class JobStatus(str, enum.Enum):
    queued = "queued"
    running = "running"
    done = "done"
    failed = "failed"
    cancelled = "cancelled"

class UploadKind(str, enum.Enum):
    pdf = "pdf"
    excel = "excel"
    docx = "docx"
    csv = "csv"
    image = "image"
    other = "other"

class User(Base):
    __tablename__ = "users"
    id = Column(String(36), primary_key=True, default=gen_uuid)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    
    # Profile fields
    full_name = Column(String)
    avatar_url = Column(String)
    department = Column(String)
    job_title = Column(String)
    
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    roles = relationship("UserRole", back_populates="user")
    uploads = relationship("Upload", back_populates="user")
    jobs = relationship("Job", back_populates="user")

class UserRole(Base):
    __tablename__ = "user_roles"
    id = Column(String(36), primary_key=True, default=gen_uuid)
    user_id = Column(String(36), ForeignKey("users.id"))
    role = Column(Enum(AppRole), default=AppRole.guest)
    
    user = relationship("User", back_populates="roles")

class Module(Base):
    __tablename__ = "modules"
    id = Column(String(36), primary_key=True, default=gen_uuid)
    key = Column(String, unique=True, index=True)
    name = Column(String)
    description = Column(String)
    icon = Column(String)
    category = Column(String)
    enabled = Column(Boolean, default=True)
    sort_order = Column(Integer, default=0)

class Upload(Base):
    __tablename__ = "uploads"
    id = Column(String(36), primary_key=True, default=gen_uuid)
    user_id = Column(String(36), ForeignKey("users.id"))
    original_name = Column(String)
    storage_path = Column(String) # Relative path on local disk
    kind = Column(Enum(UploadKind))
    mime = Column(String)
    size_bytes = Column(Integer)
    metadata_json = Column(JSON, default=dict)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    user = relationship("User", back_populates="uploads")
    
class Job(Base):
    __tablename__ = "jobs"
    id = Column(String(36), primary_key=True, default=gen_uuid)
    user_id = Column(String(36), ForeignKey("users.id"))
    module_key = Column(String, ForeignKey("modules.key"))
    status = Column(Enum(JobStatus), default=JobStatus.queued)
    
    # Store references to uploads
    input_refs = Column(JSON, default=dict)
    output_refs = Column(JSON, default=dict)
    
    logs = Column(JSON, default=list)
    error_message = Column(String, nullable=True)
    progress = Column(Integer, default=0)
    
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    user = relationship("User", back_populates="jobs")
