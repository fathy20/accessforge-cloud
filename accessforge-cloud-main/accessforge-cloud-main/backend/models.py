from sqlalchemy import Column, String, Unicode, UnicodeText, Boolean, Integer, DateTime, ForeignKey, Enum, JSON, Text
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
    email = Column(String(255), unique=True, index=True)
    hashed_password = Column(String(255))
    
    # Profile fields
    full_name = Column(Unicode(255))
    avatar_url = Column(String(512), nullable=True)
    department = Column(Unicode(255), nullable=True)
    job_title = Column(Unicode(255), nullable=True)
    phone = Column(String(64), nullable=True)
    employee_id = Column(String(64), nullable=True)
    status = Column(String(32), default="active")
    last_seen_at = Column(DateTime(timezone=True), nullable=True)
    
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    roles = relationship("UserRole", back_populates="user")
    uploads = relationship("Upload", back_populates="user")
    jobs = relationship("Job", back_populates="user")
    projects = relationship("Project", back_populates="owner")
    notifications = relationship("Notification", back_populates="user")

class UserRole(Base):
    __tablename__ = "user_roles"
    id = Column(String(36), primary_key=True, default=gen_uuid)
    user_id = Column(String(36), ForeignKey("users.id"))
    role = Column(Enum(AppRole), default=AppRole.guest)
    
    user = relationship("User", back_populates="roles")

class Module(Base):
    __tablename__ = "modules"
    id = Column(String(36), primary_key=True, default=gen_uuid)
    key = Column(String(128), unique=True, index=True)
    name = Column(Unicode(255))
    description = Column(Unicode(1024), nullable=True)
    icon = Column(String(128), nullable=True)
    category = Column(Unicode(128), nullable=True)
    enabled = Column(Boolean, default=True)
    sort_order = Column(Integer, default=0)

class Upload(Base):
    __tablename__ = "uploads"
    id = Column(String(36), primary_key=True, default=gen_uuid)
    user_id = Column(String(36), ForeignKey("users.id"))
    original_name = Column(Unicode(512))
    storage_path = Column(String(1024))
    kind = Column(Enum(UploadKind))
    mime = Column(String(128))
    size_bytes = Column(Integer)
    metadata_json = Column(JSON, default=dict)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    user = relationship("User", back_populates="uploads")
    
class Job(Base):
    __tablename__ = "jobs"
    id = Column(String(36), primary_key=True, default=gen_uuid)
    user_id = Column(String(36), ForeignKey("users.id"))
    module_key = Column(String(128), ForeignKey("modules.key"))
    status = Column(Enum(JobStatus), default=JobStatus.queued)
    
    input_refs = Column(JSON, default=dict)
    output_refs = Column(JSON, default=dict)
    
    logs = Column(JSON, default=list)
    error_message = Column(UnicodeText().with_variant(Unicode(), "mssql"), nullable=True)
    progress = Column(Integer, default=0)
    
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    user = relationship("User", back_populates="jobs")

class Project(Base):
    __tablename__ = "projects"
    id = Column(String(36), primary_key=True, default=gen_uuid)
    owner_id = Column(String(36), ForeignKey("users.id"))
    name = Column(Unicode(255))
    code = Column(String(64), nullable=True)
    description = Column(UnicodeText().with_variant(Unicode(), "mssql"), nullable=True)
    status = Column(String(32), default="active")
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    owner = relationship("User", back_populates="projects")

class AuditLog(Base):
    __tablename__ = "audit_log"
    id = Column(String(36), primary_key=True, default=gen_uuid)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=True)
    actor_name = Column(Unicode(255), nullable=True)
    action = Column(String(128))
    entity = Column(String(128), nullable=True)
    entity_id = Column(String(128), nullable=True)
    metadata_json = Column(JSON, default=dict)
    ts = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

class Notification(Base):
    __tablename__ = "notifications"
    id = Column(String(36), primary_key=True, default=gen_uuid)
    user_id = Column(String(36), ForeignKey("users.id"))
    kind = Column(String(64))
    title = Column(Unicode(255))
    body = Column(UnicodeText().with_variant(Unicode(), "mssql"), nullable=True)
    link = Column(String(512), nullable=True)
    read_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    user = relationship("User", back_populates="notifications")

class UserInvitation(Base):
    __tablename__ = "user_invitations"
    id = Column(String(36), primary_key=True, default=gen_uuid)
    email = Column(String(255), index=True)
    role = Column(String(64))
    token = Column(String(128), unique=True)
    invited_by = Column(String(36), ForeignKey("users.id"))
    accepted_at = Column(DateTime(timezone=True), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

class ModuleAccess(Base):
    __tablename__ = "module_access"
    id = Column(String(36), primary_key=True, default=gen_uuid)
    user_id = Column(String(36), ForeignKey("users.id"))
    module_id = Column(String(36), ForeignKey("modules.id"))
    enabled = Column(Boolean, default=True)
    granted_by = Column(String(36), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
