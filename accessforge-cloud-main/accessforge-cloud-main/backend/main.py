import os
import logging
import shutil
from pathlib import Path
from typing import List

from fastapi import FastAPI, UploadFile, File, Depends, BackgroundTasks, Form, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.exc import NoSuchTableError
from sqlalchemy.orm import Session
from typing import Optional
import tempfile
import sys
from pydantic import BaseModel
import traceback
import json

from .config import get_app_env, should_auto_create_schema
from .database import engine, Base, get_db
from .models import (
    Job,
    JobStatus,
    Module,
    ModuleAccess,
    ModuleStatus,
    Notification,
    Upload,
    UploadKind,
    User,
)
from .auth import router as auth_router, get_current_user
from .admin_routes import router as admin_router
from .project_routes import router as project_router
from .statistics.router import router as statistics_router
from .rbac.permissions import get_effective_permissions, record_audit
from . import storage as storage_backend
from .tools.sync_registry import sync_registry

logger = logging.getLogger(__name__)
APP_ENV = get_app_env()


def _create_schema_if_allowed() -> None:
    if should_auto_create_schema(APP_ENV, engine.dialect.name):
        Base.metadata.create_all(bind=engine)
        return
    if APP_ENV == "production":
        logger.info("Production schema management: Alembic owns the schema; skipping create_all.")
    else:
        logger.info("Automatic schema creation disabled; Alembic owns non-SQLite schemas.")


_create_schema_if_allowed()

app = FastAPI(title="Redsea Local Backend")


def _database_dialect_only() -> str:
    dialect = getattr(getattr(engine, "dialect", None), "name", "unknown")
    return dialect if dialect in {"sqlite", "mssql", "postgresql", "mysql", "oracle"} else "unknown"


def _expected_migration_head() -> str | None:
    """Load the Alembic head from local scripts without touching a database."""

    try:
        from alembic.config import Config
        from alembic.script import ScriptDirectory

        config_path = Path(__file__).resolve().parents[1] / "alembic.ini"
        config = Config(str(config_path))
        script_directory = ScriptDirectory.from_config(config)
        heads = script_directory.get_heads()
        return heads[0] if len(heads) == 1 else None
    except Exception:
        return None


def _migration_table_is_missing(exc: Exception) -> bool:
    if isinstance(exc, NoSuchTableError):
        return True

    message = str(exc).casefold()
    if "alembic_version" not in message:
        return False
    return any(
        marker in message
        for marker in ("no such table", "invalid object name", "does not exist")
    )


def _migration_state(connection) -> str:
    expected_head = _expected_migration_head()
    if expected_head is None:
        return "unavailable"

    try:
        result = connection.execute(text("SELECT version_num FROM alembic_version"))
        revisions = [row[0] for row in result.fetchall()]
    except Exception as exc:
        return "unmanaged" if _migration_table_is_missing(exc) else "unavailable"

    return "current" if revisions == [expected_head] else "behind"


@app.get("/health/live")
def health_live():
    return {"status": "ok"}


@app.get("/health/ready")
def health_ready():
    dialect = _database_dialect_only()
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
            migration = _migration_state(connection)
    except Exception:
        logger.warning("Database readiness probe failed.")
        return JSONResponse(
            status_code=503,
            content={"status": "degraded", "dialect": dialect, "migration": "unavailable"},
        )

    return {"status": "ok", "dialect": dialect, "migration": migration}

CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:3000,http://localhost:5173").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(project_router)
app.include_router(statistics_router)

@app.get("/api/notifications")
def get_notifications(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    notifs = db.query(Notification).filter(Notification.user_id == current_user.id).order_by(Notification.created_at.desc()).limit(50).all()
    return notifs

@app.post("/api/notifications/{notification_id}/read")
def mark_notification_read(notification_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    from datetime import datetime, timezone
    notif = db.query(Notification).filter(Notification.id == notification_id, Notification.user_id == current_user.id).first()
    if notif:
        notif.read_at = datetime.now(timezone.utc)
        db.commit()
    return {"status": "success"}

@app.post("/api/notifications/read-all")
def mark_all_notifications_read(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    from datetime import datetime, timezone
    db.query(Notification).filter(Notification.user_id == current_user.id, Notification.read_at == None).update(
        {Notification.read_at: datetime.now(timezone.utc)}
    )
    db.commit()
    return {"status": "success"}

UPLOAD_DIR = storage_backend.UPLOAD_DIR
OUTPUT_DIR = storage_backend.OUTPUT_DIR

# ---------------------------------------------
# Uploads API
# ---------------------------------------------
MAX_UPLOAD_SIZE = 100 * 1024 * 1024  # 100 MB

@app.post("/api/uploads")
async def upload_files(
    files: List[UploadFile] = File(...), 
    db: Session = Depends(get_db), 
    current_user: User = Depends(get_current_user)
):
    results = []
    for file in files:
        try:
            artifact = await storage_backend.store_upload(
                file,
                UPLOAD_DIR,
                MAX_UPLOAD_SIZE,
            )
        except storage_backend.UploadTooLargeError as exc:
            raise HTTPException(status_code=413, detail=str(exc)) from exc
        except storage_backend.UnsupportedArtifactError as exc:
            raise HTTPException(status_code=415, detail=str(exc)) from exc
        except storage_backend.StorageConflictError:
            logger.exception("Generated upload storage target already exists.")
            raise HTTPException(status_code=500, detail="Could not store upload.") from None
        except OSError:
            logger.exception("Upload filesystem operation failed.")
            raise HTTPException(status_code=500, detail="Could not store upload.") from None

        scan_state = storage_backend.scan_artifact(artifact.path)
        upload = Upload(
            user_id=current_user.id,
            original_name=artifact.original_name,
            storage_path=str(artifact.path),
            kind=UploadKind(artifact.kind),
            mime=artifact.mime,
            size_bytes=artifact.size_bytes,
            sha256=artifact.sha256,
            scan_state=scan_state,
            retention_expires_at=storage_backend.retention_expires_at(),
        )
        try:
            db.add(upload)
            db.flush()
            record_audit(
                db,
                current_user,
                "upload",
                "upload",
                upload.id,
                artifact_type="upload",
                original_name=upload.original_name,
                size=upload.size_bytes,
                size_bytes=upload.size_bytes,
                sha256=upload.sha256,
                mime=upload.mime,
                scan_state=upload.scan_state,
            )
            db.commit()
            db.refresh(upload)
        except Exception:
            db.rollback()
            try:
                storage_backend.delete_artifact_file(UPLOAD_DIR, artifact.path)
            except Exception:
                logger.exception("Could not remove upload after database failure.")
            raise

        results.append({
            "id": upload.id,
            "original_name": upload.original_name,
            "kind": upload.kind,
            "created_at": upload.created_at
        })
        
    return results

@app.get("/api/uploads")
def get_uploads(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    uploads = db.query(Upload).filter(Upload.user_id == current_user.id).order_by(Upload.created_at.desc()).limit(100).all()
    return uploads

@app.delete("/api/uploads/{upload_id}")
def delete_upload(upload_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    upload = db.query(Upload).filter(Upload.id == upload_id, Upload.user_id == current_user.id).first()
    if not upload:
        raise HTTPException(status_code=404, detail="Upload not found")

    filesystem_error = None
    try:
        storage_backend.delete_artifact_file(UPLOAD_DIR, upload.storage_path)
    except Exception as exc:
        filesystem_error = type(exc).__name__
        logger.warning(
            "Upload artifact filesystem deletion failed.",
            extra={"upload_id": str(upload.id), "failure_kind": filesystem_error},
        )

    db.delete(upload)
    record_audit(
        db,
        current_user,
        "delete",
        "upload",
        upload.id,
        artifact_type="upload",
        original_name=upload.original_name,
        size=upload.size_bytes,
        size_bytes=upload.size_bytes,
        sha256=upload.sha256,
        mime=upload.mime,
        filesystem_status="deleted" if filesystem_error is None else "failed",
        filesystem_error=filesystem_error,
    )
    db.commit()

    if filesystem_error is not None:
        raise HTTPException(
            status_code=500,
            detail="Upload metadata was removed but the artifact file could not be removed.",
        )
    return {"status": "success"}

@app.get("/api/uploads/{upload_id}/download")
def download_upload(upload_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    upload = db.query(Upload).filter(Upload.id == upload_id, Upload.user_id == current_user.id).first()
    if not upload:
        raise HTTPException(status_code=404, detail="File not found")
    try:
        file_path = storage_backend.existing_artifact_path(UPLOAD_DIR, upload.storage_path)
    except (OSError, storage_backend.StorageError):
        raise HTTPException(status_code=404, detail="File not found") from None

    record_audit(
        db,
        current_user,
        "download",
        "upload",
        upload.id,
        artifact_type="upload",
        original_name=upload.original_name,
        size=upload.size_bytes,
        size_bytes=upload.size_bytes,
        sha256=upload.sha256,
        mime=upload.mime,
    )
    db.commit()
    return FileResponse(
        path=file_path,
        filename=storage_backend.sanitize_original_name(upload.original_name),
        media_type=upload.mime,
    )

# ---------------------------------------------
# Jobs API
# ---------------------------------------------
class CreateJobRequest(BaseModel):
    module_key: str
    input_refs: dict

from backend.database import SessionLocal

def run_job_background(job_id: str):
    with SessionLocal() as db:
        job = db.query(Job).filter(Job.id == job_id).first()
        if not job:
            return
            
        job.status = JobStatus.running
        db.commit()
        
        def log_progress(progress: int, msg: str):
            with SessionLocal() as _db:
                _j = _db.query(Job).filter(Job.id == job_id).first()
                if _j:
                    _j.progress = progress
                    _j.logs = list(_j.logs) + [{"level": progress, "msg": msg}]
                    _db.commit()
            
        workdir = None
        try:
            sys.path.append(str(Path(__file__).parent.parent))
            from worker.handlers import REGISTRY
            
            module_key = job.module_key
            handler = REGISTRY.get(module_key)
            if not handler:
                raise ValueError(f"Module {module_key} not found in registry")
                
            # Get input files
            file_ids = job.input_refs.get("files", [])
            input_files = []
            for fid in file_ids:
                upload = db.query(Upload).filter(Upload.id == fid).first()
                if upload:
                    input_files.append(upload.storage_path)
                    
            if not input_files and job.input_refs.get("data_source") != "db":
                raise ValueError("No valid input files found for job")
                
            # Setup workdir
            workdir = Path(tempfile.gettempdir()) / "redsea_backend" / str(job.id)
            (workdir / "in").mkdir(parents=True, exist_ok=True)
            (workdir / "out").mkdir(parents=True, exist_ok=True)
            
            # Convert SQLAlchemy object to dict for the handler
            job_dict = {
                "id": str(job.id),
                "input_refs": job.input_refs
            }
            
            log_progress(10, f"Starting module {module_key} with {len(input_files)} files")
            
            # Execute handler
            out_paths = handler(job_dict, input_files, workdir, log_progress)
            
            # Process outputs
            output_refs = {"files": []}
            output_artifacts = []
            for path_str in out_paths:
                path = Path(path_str)
                try:
                    artifact = storage_backend.persist_output_artifact(path, OUTPUT_DIR)
                except FileNotFoundError:
                    logger.warning("Generated output was not found.", extra={"job_id": str(job.id)})
                    continue

                output_artifacts.append(artifact)
                base_url = os.getenv("BASE_URL", "http://localhost:8000")
                output_refs["files"].append({
                    "id": artifact.storage_name,
                    "name": artifact.original_name,
                    "original_name": artifact.original_name,
                    "storage_name": artifact.storage_name,
                    "size_bytes": artifact.size_bytes,
                    "sha256": artifact.sha256,
                    "mime": artifact.mime,
                    "url": f"{base_url}/api/downloads/{artifact.storage_name}",
                })

            with SessionLocal() as _db:
                _j = _db.query(Job).filter(Job.id == job_id).first()
                _j.status = JobStatus.done
                _j.progress = 100
                _j.output_refs = output_refs
                output_owner = _db.query(User).filter(User.id == job.user_id).first()
                for artifact in output_artifacts:
                    record_audit(
                        _db,
                        output_owner,
                        "upload",
                        "output",
                        artifact.storage_name,
                        artifact_type="output",
                        original_name=artifact.original_name,
                        size=artifact.size_bytes,
                        size_bytes=artifact.size_bytes,
                        sha256=artifact.sha256,
                        mime=artifact.mime,
                    )
                _db.commit()
                
        except Exception as e:
            with SessionLocal() as _db:
                _j = _db.query(Job).filter(Job.id == job_id).first()
                if _j:
                    _j.status = JobStatus.failed
                    _j.error_message = str(e)
                    _j.logs = list(_j.logs) + [{"level": 99, "msg": traceback.format_exc()}]
                    _db.commit()
        finally:
            # Clean up the temporary workspace
            try:
                if workdir and workdir.exists():
                    shutil.rmtree(workdir)
            except Exception as e:
                print(f"Failed to cleanup temp dir {workdir}: {e}")

@app.post("/api/jobs")
def create_job(
    req: CreateJobRequest, 
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db), 
    current_user: User = Depends(get_current_user)
):
    from worker.handlers import REGISTRY
    if req.module_key not in REGISTRY:
        raise HTTPException(status_code=422, detail=f"Unknown module: {req.module_key}")

    job = Job(
        user_id=current_user.id,
        module_key=req.module_key,
        input_refs=req.input_refs,
        status=JobStatus.queued
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    
    background_tasks.add_task(run_job_background, str(job.id))
    
    return {"id": job.id, "status": job.status}

def _output_entry_storage_name(job: Job, entry: dict) -> str:
    for key in ("storage_name", "storage_path", "url"):
        value = entry.get(key)
        if value:
            return storage_backend.storage_basename(str(value).split("?", 1)[0])

    original_name = storage_backend.sanitize_original_name(entry.get("name"))
    return f"{job.user_id}_{job.id}_{original_name}"


def _owned_output_artifact(db: Session, user_id: str, filename: str) -> dict | None:
    requested_name = storage_backend.storage_basename(filename)
    jobs = db.query(Job).filter(Job.user_id == user_id).all()
    for job in jobs:
        output_refs = job.output_refs or {}
        for entry in output_refs.get("files", []):
            if not isinstance(entry, dict):
                continue
            storage_name = _output_entry_storage_name(job, entry)
            if storage_name not in {filename, requested_name}:
                continue
            return {
                "id": str(entry.get("id") or f"{job.id}:{storage_name}"),
                "storage_name": storage_name,
                "original_name": storage_backend.sanitize_original_name(
                    entry.get("original_name") or entry.get("name") or storage_name
                ),
                "size_bytes": entry.get("size_bytes"),
                "sha256": entry.get("sha256"),
                "mime": entry.get("mime"),
            }
    return None


@app.get("/api/downloads/{filename}")
def download_file(
    filename: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Authorization is DB-scoped and completes before the filesystem is probed.
    artifact = _owned_output_artifact(db, current_user.id, filename)
    if artifact is None:
        raise HTTPException(status_code=404, detail="File not found")

    try:
        file_path = storage_backend.existing_artifact_path(
            OUTPUT_DIR,
            filename,
            relative_to_root=True,
        )
    except (OSError, storage_backend.StorageError):
        raise HTTPException(status_code=404, detail="File not found") from None

    if (
        artifact["size_bytes"] is None
        or artifact["sha256"] is None
        or artifact["mime"] is None
    ):
        described = storage_backend.describe_artifact(
            file_path,
            artifact["original_name"],
        )
        artifact["size_bytes"] = described.size_bytes
        artifact["sha256"] = described.sha256
        artifact["mime"] = described.mime

    record_audit(
        db,
        current_user,
        "download",
        "output",
        artifact["id"],
        artifact_type="output",
        original_name=artifact["original_name"],
        size=artifact["size_bytes"],
        size_bytes=artifact["size_bytes"],
        sha256=artifact["sha256"],
        mime=artifact["mime"],
    )
    db.commit()
    return FileResponse(
        path=file_path,
        filename=artifact["original_name"],
        media_type=artifact["mime"],
    )

@app.get("/api/jobs")
def get_jobs(
    module_key: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    query = db.query(Job).filter(Job.user_id == current_user.id)
    if module_key:
        query = query.filter(Job.module_key == module_key)
    if status:
        query = query.filter(Job.status == status)
    jobs = query.order_by(Job.created_at.desc()).limit(limit).all()
    return jobs

@app.get("/api/jobs/{job_id}")
def get_job(job_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    job = db.query(Job).filter(Job.id == job_id, Job.user_id == current_user.id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job

# ---------------------------------------------
# Modules / Config API
# ---------------------------------------------
@app.get("/api/modules")
def get_modules(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    permissions = get_effective_permissions(db, current_user)
    disabled_module_ids = {
        module_id
        for (module_id,) in db.query(ModuleAccess.module_id)
        .filter(ModuleAccess.user_id == current_user.id, ModuleAccess.enabled == False)  # noqa: E712
        .all()
    }
    modules = db.query(Module).order_by(Module.sort_order, Module.key).all()
    return [
        _module_payload(module, permissions)
        for module in modules
        if _module_is_visible(module, permissions, disabled_module_ids)
    ]


@app.get("/api/modules/{module_key}")
def get_module(
    module_key: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    module = db.query(Module).filter(Module.key == module_key).first()
    if module is None:
        raise HTTPException(status_code=404, detail="Module not found")

    permissions = get_effective_permissions(db, current_user)
    disabled_module_ids = {
        module_id
        for (module_id,) in db.query(ModuleAccess.module_id)
        .filter(ModuleAccess.user_id == current_user.id, ModuleAccess.enabled == False)  # noqa: E712
        .all()
    }
    if not _module_is_visible(module, permissions, disabled_module_ids):
        raise HTTPException(status_code=403, detail="Module access denied")
    return _module_payload(module, permissions)


def _enum_value(value):
    return value.value if hasattr(value, "value") else value


def _module_payload(module: Module, permissions: set[str]) -> dict:
    return {
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
        "granted_action_permissions": sorted(set(module.action_permissions or []) & permissions),
    }


def _module_is_visible(
    module: Module,
    permissions: set[str],
    disabled_module_ids: set[str],
) -> bool:
    return (
        bool(module.enabled)
        and module.module_status != ModuleStatus.hidden
        and module.id not in disabled_module_ids
        and bool(module.required_view_permission)
        and module.required_view_permission in permissions
    )

# ---------------------------------------------
# App Init
# ---------------------------------------------
@app.on_event("startup")
def startup_db_seed():
    db = next(get_db())
    try:
        sync_registry(db)
    finally:
        db.close()
