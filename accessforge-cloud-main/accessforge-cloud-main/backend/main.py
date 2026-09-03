import os
import logging
import shutil
from contextlib import asynccontextmanager
from pathlib import Path
from typing import List

from datetime import datetime, time, timedelta, timezone

from fastapi import FastAPI, UploadFile, File, Depends, BackgroundTasks, HTTPException, Query, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, text
from sqlalchemy.exc import NoSuchTableError
from sqlalchemy.orm import Session
from typing import Optional
import tempfile
from pydantic import BaseModel
import traceback

from .config import get_app_env, job_execution_mode, resolve_cors_origins, should_auto_create_schema
from .database import engine, Base, get_db
from .models import (
    Job,
    JobStatus,
    Module,
    ModuleAccess,
    ModuleStatus,
    Notification,
    Project,
    Upload,
    UploadKind,
    User,
)
from .auth import router as auth_router, get_current_user
from .admin_routes import router as admin_router
from .project_routes import router as project_router
from .statistics.router import router as statistics_router
from .copilot.router import router as copilot_router
from .rbac.permissions import get_effective_permissions, record_audit
from .module_visibility import module_is_visible, module_visibility_inputs
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


def startup_db_seed() -> None:
    """Project the code-owned registry into SQL, tolerating a concurrent sync.

    With several workers, two processes can run this at once; the loser hits a
    unique-key conflict. If a projection already exists the database is in the
    desired state, so the conflict is logged and startup continues. An empty
    projection with a failing sync is fatal — the app would run with no
    visible modules.
    """

    from backend.database import SessionLocal as _SessionLocal

    db = _SessionLocal()
    try:
        try:
            sync_registry(db)
        except Exception:
            db.rollback()
            if db.query(Module).count() == 0:
                raise
            logger.warning(
                "Registry sync failed but a module projection exists; continuing.",
                exc_info=True,
            )
    finally:
        db.close()


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    startup_db_seed()
    yield


app = FastAPI(title="Redsea Local Backend", lifespan=_lifespan)


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

CORS_ORIGINS = resolve_cors_origins(APP_ENV)
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition", "X-Total-Count"],
)

app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(project_router)
app.include_router(statistics_router)
app.include_router(copilot_router)

# --- Response serializers -----------------------------------------------------
# Endpoints return explicit shapes, never raw ORM rows: a raw row leaks server
# internals (absolute storage paths, worker tracebacks) and silently widens the
# API contract every time a column is added.


def _notification_payload(notification: Notification) -> dict:
    return {
        "id": notification.id,
        "kind": notification.kind,
        "title": notification.title,
        "body": notification.body,
        "link": notification.link,
        "read_at": notification.read_at,
        "created_at": notification.created_at,
    }


def _upload_payload(upload: Upload) -> dict:
    return {
        "id": upload.id,
        "original_name": upload.original_name,
        "kind": _enum_value(upload.kind),
        "mime": upload.mime,
        "size_bytes": upload.size_bytes,
        "sha256": upload.sha256,
        "scan_state": upload.scan_state,
        "retention_expires_at": upload.retention_expires_at,
        "created_at": upload.created_at,
    }


def _job_payload(job: Job) -> dict:
    return {
        "id": job.id,
        "module_key": job.module_key,
        "status": _enum_value(job.status),
        "progress": job.progress,
        "error_message": job.error_message,
        "output_refs": job.output_refs or {},
        "created_at": job.created_at,
        "started_at": job.started_at,
        "completed_at": job.completed_at,
        "attempt": job.attempt or 0,
        "cancel_requested": bool(job.cancel_requested),
    }


@app.get("/api/notifications")
def get_notifications(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    notifs = db.query(Notification).filter(Notification.user_id == current_user.id).order_by(Notification.created_at.desc()).limit(50).all()
    return [_notification_payload(n) for n in notifs]

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
MAX_FILES_PER_UPLOAD = 20

@app.post("/api/uploads")
async def upload_files(
    files: List[UploadFile] = File(...), 
    db: Session = Depends(get_db), 
    current_user: User = Depends(get_current_user)
):
    if len(files) > MAX_FILES_PER_UPLOAD:
        raise HTTPException(
            status_code=413,
            detail=f"At most {MAX_FILES_PER_UPLOAD} files per request.",
        )
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

        results.append(_upload_payload(upload))

    return results

@app.get("/api/uploads")
def get_uploads(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    uploads = db.query(Upload).filter(Upload.user_id == current_user.id).order_by(Upload.created_at.desc()).limit(100).all()
    return [_upload_payload(upload) for upload in uploads]

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


# Column 24 of an MPD RSD sheet is free text, and app2 deliberately filters
# nothing out of it ("باقي كل حاجة نضيفها", app2.py:3409). A crafted or merely
# enormous workbook could therefore hold a huge number of very long distinct
# strings and turn one dropdown fetch into a multi-megabyte response. Both caps
# bound the RESPONSE; neither changes which codes a normal workbook yields.
MAX_CHECK_CODES = 500
MAX_CHECK_CODE_LENGTH = 64
# Column 24 is the 25th column, so the sheet must be wider than 24 columns.
CHECK_CODE_COLUMN_INDEX = 24


def _read_mpd_rsd_frame(file_path: Path):
    """Load the MPD RSD sheet the way the desktop app does.

    Mirrors ``RedseaApp._extract_available_checks_from_excel``
    (app2.py:3363-3387) for the no-sheet-name case: ``.xlsb`` needs the pyxlsb
    engine and picks the first sheet whose upper-cased name contains
    ``MPD RSD``, falling back to the first sheet; every other format is read as
    sheet 0.
    """

    import pandas as pd

    path_text = str(file_path)
    if path_text.lower().endswith(".xlsb"):
        workbook = pd.ExcelFile(path_text, engine="pyxlsb")
        try:
            sheet_names = list(workbook.sheet_names)
        finally:
            workbook.close()
        if not sheet_names:
            return None
        target = next(
            (name for name in sheet_names if "MPD RSD" in str(name).upper()),
            sheet_names[0],
        )
        return pd.read_excel(path_text, sheet_name=target, engine="pyxlsb")
    return pd.read_excel(path_text, sheet_name=0)


def _extract_check_codes(file_path: Path) -> list:
    """Distinct, sorted column-24 values, mirroring app2.py:3402-3419.

    Only blank / ``nan`` / ``none`` cells are dropped -- there is no known-code
    allow-list, because the whole point is that the operator's workbook, not a
    hardcoded list, decides which checks exist.
    """

    try:
        frame = _read_mpd_rsd_frame(file_path)
    except ImportError:
        # A missing pandas/pyxlsb is a deployment fault, not a property of the
        # workbook. It still degrades to the hardcoded dropdown rather than a
        # 500, but it must not be logged as if the file were simply empty --
        # that is how a silently reinstated hardcoded list would go unnoticed.
        logger.warning(
            "Check-code extraction is unavailable: a spreadsheet dependency is "
            "not installed. See backend/requirements.txt (pandas, pyxlsb).",
            exc_info=True,
        )
        return []
    except Exception:
        # Not a readable spreadsheet, or a corrupt workbook. The desktop app
        # logs and returns an empty list here; an empty dropdown is a
        # legitimate answer, so this must not become a 500.
        logger.info(
            "Could not read a workbook for check-code extraction.",
            exc_info=True,
        )
        return []

    if frame is None or frame.shape[1] <= CHECK_CODE_COLUMN_INDEX:
        return []

    codes = set()
    for value in frame.iloc[:, CHECK_CODE_COLUMN_INDEX].astype(str):
        cleaned = str(value).strip()
        if not cleaned or cleaned.lower() in ("nan", "none"):
            continue
        if len(cleaned) > MAX_CHECK_CODE_LENGTH:
            # Skipped rather than truncated: a truncated code is not the code,
            # and offering it would submit a check the workbook never contains
            # -- the same silent zero-card outcome this endpoint exists to fix.
            continue
        codes.add(cleaned)
        if len(codes) >= MAX_CHECK_CODES:
            break
    return sorted(codes)


@app.get("/api/uploads/{upload_id}/check-codes")
def get_upload_check_codes(
    upload_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List the check codes an uploaded MPD RSD workbook actually contains.

    The desktop app repopulates its "Check:" combo from column 24 of the chosen
    workbook the moment it is picked (``_pick_mpd_rsd_excel`` ->
    ``_refresh_available_checks``, app2.py:2916/3288). The web UI had a
    hardcoded list instead, so an unlisted code was unselectable and a listed
    code the workbook lacked ran a job that produced nothing.

    A missing or another user's upload is a 404; anything else -- unreadable
    file, too-few columns, no non-empty values -- is ``{"codes": []}`` with 200.
    """

    upload = db.query(Upload).filter(Upload.id == upload_id, Upload.user_id == current_user.id).first()
    if not upload:
        raise HTTPException(status_code=404, detail="Upload not found")
    try:
        file_path = storage_backend.existing_artifact_path(UPLOAD_DIR, upload.storage_path)
    except (OSError, storage_backend.StorageError):
        raise HTTPException(status_code=404, detail="Upload not found") from None

    return {"codes": _extract_check_codes(file_path)}


# ---------------------------------------------
# Jobs API
# ---------------------------------------------
class CreateJobRequest(BaseModel):
    module_key: str
    input_refs: dict

from backend.database import SessionLocal  # noqa: F401 - re-exported for tests/tools
from .job_runner import (  # noqa: F401 - re-exported names
    MAX_JOB_LOG_ENTRIES,
    _append_job_log,
    run_job_background,
)
from .job_queue import request_cancel, requeue_for_retry


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

    module = db.query(Module).filter(Module.key == req.module_key).first()
    permissions, disabled_module_ids = _module_visibility_inputs(db, current_user)
    if not _module_is_visible(module, permissions, disabled_module_ids):
        record_audit(
            db,
            current_user,
            "job_module_denied",
            "job",
            None,
            module_key=req.module_key,
        )
        db.commit()
        raise HTTPException(status_code=403, detail="Module access denied")

    file_ids = req.input_refs.get("files", [])
    rejected_file_count = 0
    for fid in file_ids:
        upload = (
            db.query(Upload)
            .filter(Upload.id == fid, Upload.user_id == current_user.id)
            .first()
        )
        if upload is None:
            rejected_file_count += 1

    if rejected_file_count:
        record_audit(
            db,
            current_user,
            "job_input_rejected",
            "job",
            None,
            rejected_count=rejected_file_count,
        )
        db.commit()
        raise HTTPException(status_code=400, detail="Unknown or inaccessible input file")

    job = Job(
        user_id=current_user.id,
        module_key=req.module_key,
        input_refs=req.input_refs,
        status=JobStatus.queued
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    # inline: run in this process (development, tests). worker: the row is
    # the queue entry; `python -m worker.runner` claims and executes it.
    if job_execution_mode() == "inline":
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
    # Outputs only exist on completed jobs; the filter keeps this Python-side
    # scan from touching every job the user ever ran. A relational outputs
    # table is the real fix and belongs to the durable-jobs slice.
    jobs = (
        db.query(Job)
        .filter(Job.user_id == user_id, Job.status == JobStatus.done)
        .order_by(Job.created_at.desc())
        .all()
    )
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
    response: Response,
    module_key: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = Query(100, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Newest-first page of the caller's jobs.

    The body stays a plain list for existing clients; the page size and
    position come from ``limit``/``offset`` and the unpaged total travels in
    the ``X-Total-Count`` header.
    """
    query = db.query(Job).filter(Job.user_id == current_user.id)
    if module_key:
        query = query.filter(Job.module_key == module_key)
    if status:
        query = query.filter(Job.status == status)
    response.headers["X-Total-Count"] = str(query.count())
    jobs = query.order_by(Job.created_at.desc()).offset(offset).limit(limit).all()
    return [_job_payload(job) for job in jobs]


DASHBOARD_HISTORY_DAYS = 14
DASHBOARD_RECENT_LIMIT = 6
DASHBOARD_TOP_MODULES = 8


@app.get("/api/dashboard/summary")
def get_dashboard_summary(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Everything the dashboard shows, aggregated in SQL.

    The page used to download the caller's complete job and upload lists on
    every poll and reduce them in the browser. Grouping here means each poll
    moves a few dozen numbers and two six-row lists regardless of history size.
    """
    own_jobs = db.query(Job).filter(Job.user_id == current_user.id)

    by_status = {status.value: 0 for status in JobStatus}
    for status, count in (
        db.query(Job.status, func.count(Job.id))
        .filter(Job.user_id == current_user.id)
        .group_by(Job.status)
        .all()
    ):
        by_status[_enum_value(status)] = count

    by_module = [
        {"module_key": module_key, "count": count}
        for module_key, count in (
            db.query(Job.module_key, func.count(Job.id))
            .filter(Job.user_id == current_user.id)
            .group_by(Job.module_key)
            .order_by(func.count(Job.id).desc(), Job.module_key)
            .limit(DASHBOARD_TOP_MODULES)
            .all()
        )
    ]

    # Daily buckets are built in Python on purpose: the window is bounded and
    # only two columns travel, and it avoids a dialect-specific date()
    # expression so SQLite and SQL Server produce identical results. Days are
    # UTC calendar days.
    today = datetime.now(timezone.utc).date()
    first_day = today - timedelta(days=DASHBOARD_HISTORY_DAYS - 1)
    window_start = datetime.combine(first_day, time.min, tzinfo=timezone.utc)
    daily = {
        (first_day + timedelta(days=offset)).isoformat(): {"done": 0, "failed": 0}
        for offset in range(DASHBOARD_HISTORY_DAYS)
    }
    for created_at, status in (
        db.query(Job.created_at, Job.status)
        .filter(
            Job.user_id == current_user.id,
            Job.created_at >= window_start,
            Job.status.in_([JobStatus.done, JobStatus.failed]),
        )
        .all()
    ):
        if created_at is None:
            continue
        stamp = created_at if created_at.tzinfo else created_at.replace(tzinfo=timezone.utc)
        bucket = daily.get(stamp.astimezone(timezone.utc).date().isoformat())
        if bucket is not None:
            bucket[_enum_value(status)] += 1

    recent_jobs = own_jobs.order_by(Job.created_at.desc()).limit(DASHBOARD_RECENT_LIMIT).all()
    own_uploads = db.query(Upload).filter(Upload.user_id == current_user.id)
    recent_uploads = own_uploads.order_by(Upload.created_at.desc()).limit(DASHBOARD_RECENT_LIMIT).all()

    return {
        "jobs": {
            "total": sum(by_status.values()),
            "active": (by_status["queued"] + by_status["running"]) > 0,
            "by_status": by_status,
            "by_module": by_module,
            "daily": [{"day": day, **counts} for day, counts in daily.items()],
            "recent": [_job_payload(job) for job in recent_jobs],
        },
        "uploads": {
            "total": own_uploads.count(),
            "recent": [_upload_payload(upload) for upload in recent_uploads],
        },
        # Projects are shared workspaces, so this is the global count — the
        # same list /api/projects returns to every authenticated user.
        "projects": {"total": db.query(func.count(Project.id)).scalar() or 0},
    }

@app.get("/api/jobs/{job_id}")
def get_job(job_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    job = db.query(Job).filter(Job.id == job_id, Job.user_id == current_user.id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return _job_payload(job)


@app.post("/api/jobs/{job_id}/cancel")
def cancel_job(
    job_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Queued jobs are cancelled at once; a running job is flagged and the
    worker kills it at its next tick. In inline mode a running job cannot be
    interrupted, so the flag is recorded and the job finishes on its own."""

    job = db.query(Job).filter(Job.id == job_id, Job.user_id == current_user.id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    outcome = request_cancel(job)
    if outcome == "noop":
        raise HTTPException(status_code=409, detail=f"Job is already {_enum_value(job.status)}")
    record_audit(db, current_user, "job_cancel", "job", job.id, outcome=outcome)
    db.commit()
    db.refresh(job)
    return _job_payload(job)


@app.post("/api/jobs/{job_id}/retry")
def retry_job(
    job_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Requeue a failed or cancelled job. Attempts keep counting across
    retries; the inputs are re-validated by the runner, not here."""

    job = db.query(Job).filter(Job.id == job_id, Job.user_id == current_user.id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status not in (JobStatus.failed, JobStatus.cancelled):
        raise HTTPException(status_code=409, detail=f"Only failed or cancelled jobs can be retried (job is {_enum_value(job.status)})")

    requeue_for_retry(job)
    record_audit(db, current_user, "job_retry", "job", job.id)
    db.commit()
    db.refresh(job)

    if job_execution_mode() == "inline":
        background_tasks.add_task(run_job_background, str(job.id))
    return _job_payload(job)

# ---------------------------------------------
# Modules / Config API
# ---------------------------------------------
@app.get("/api/modules")
def get_modules(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    permissions, disabled_module_ids = _module_visibility_inputs(db, current_user)
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

    permissions, disabled_module_ids = _module_visibility_inputs(db, current_user)
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


# Shared with the job runner (backend/module_visibility.py); the private
# names stay as aliases for existing call sites and tests.
_module_visibility_inputs = module_visibility_inputs
_module_is_visible = module_is_visible

# App init happens in _lifespan (defined above app creation): the registry
# projection is seeded there, replacing the deprecated on_event hook.
