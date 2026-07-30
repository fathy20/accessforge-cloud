import os
import shutil
from pathlib import Path
from typing import List

from fastapi import FastAPI, UploadFile, File, Depends, BackgroundTasks, Form, HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from typing import Optional
import tempfile
import sys
from pydantic import BaseModel
import traceback
import json

from .database import engine, Base, get_db
from .models import User, UserRole, AppRole, Upload, Job, JobStatus, UploadKind, Module, Notification
from .auth import router as auth_router, get_current_user
from .admin_routes import router as admin_router
from .project_routes import router as project_router
from .statistics.router import router as statistics_router

# Create database tables
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Redsea Local Backend")

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

UPLOAD_DIR = Path("local_storage/uploads")
OUTPUT_DIR = Path("local_storage/outputs")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

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
        contents = await file.read()
        if len(contents) > MAX_UPLOAD_SIZE:
            raise HTTPException(status_code=413, detail=f"File {file.filename} exceeds 100MB limit")
        file_ext = Path(file.filename).suffix.lower()
        if file_ext == '.pdf':
            kind = UploadKind.pdf
        elif file_ext in ['.xlsx', '.xls']:
            kind = UploadKind.excel
        elif file_ext == '.csv':
            kind = UploadKind.csv
        elif file_ext in ['.doc', '.docx']:
            kind = UploadKind.docx
        elif file_ext in ['.png', '.jpg', '.jpeg']:
            kind = UploadKind.image
        else:
            kind = UploadKind.other

        # Save to disk
        safe_name = f"{current_user.id}_{file.filename}"
        file_path = UPLOAD_DIR / safe_name
        
        with open(file_path, "wb") as buffer:
            buffer.write(contents)
            
        size = file_path.stat().st_size
        
        # Create DB record
        upload = Upload(
            user_id=current_user.id,
            original_name=file.filename,
            storage_path=str(file_path),
            kind=kind,
            mime=file.content_type,
            size_bytes=size
        )
        db.add(upload)
        db.commit()
        db.refresh(upload)
        
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
    # Try deleting physical file
    try:
        if os.path.exists(upload.storage_path):
            os.remove(upload.storage_path)
    except Exception:
        pass
    db.delete(upload)
    db.commit()
    return {"status": "success"}

@app.get("/api/uploads/{upload_id}/download")
def download_upload(upload_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    upload = db.query(Upload).filter(Upload.id == upload_id, Upload.user_id == current_user.id).first()
    if not upload or not os.path.exists(upload.storage_path):
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(path=upload.storage_path, filename=upload.original_name)

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
            for path_str in out_paths:
                path = Path(path_str)
                if path.exists():
                    # Move to local storage
                    final_path = OUTPUT_DIR / f"{job.user_id}_{job.id}_{path.name}"
                    shutil.copy(path, final_path)
                    
                    # We could create an Upload record, but we just need a download URL.
                    # Let's save it directly in output_refs for now
                    base_url = os.getenv("BASE_URL", "http://localhost:8000")
                    output_refs["files"].append({
                        "name": path.name,
                        "url": f"{base_url}/api/downloads/{final_path.name}"
                    })
            
            with SessionLocal() as _db:
                _j = _db.query(Job).filter(Job.id == job_id).first()
                _j.status = JobStatus.done
                _j.progress = 100
                _j.output_refs = output_refs
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

# Add download endpoint

@app.get("/api/downloads/{filename}")
def download_file(filename: str, current_user: User = Depends(get_current_user)):
    file_path = OUTPUT_DIR / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    
    # Optional: Verify ownership if needed, assuming filename format user_id_job_id_name
    if not filename.startswith(f"{current_user.id}_"):
        raise HTTPException(status_code=403, detail="Not authorized to download this file")
        
    return FileResponse(path=file_path, filename=filename.split("_", 2)[-1])

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
    # In a real app we'd fetch from DB. Let's return the hardcoded list for now to unblock UI
    return [
        {"key": "task_extractor", "name": "Task Extractor", "enabled": True},
        {"key": "task_stamping", "name": "Task Stamping", "enabled": True},
        {"key": "effectivity", "name": "Effectivity / TCM", "enabled": True},
        {"key": "check_control", "name": "Check Control", "enabled": True},
        {"key": "utilization", "name": "Utilization", "enabled": True},
        {"key": "cmp_tcm", "name": "CMP / TCM", "enabled": True},
        {"key": "cover_merge", "name": "Cover Merge", "enabled": True},
        {"key": "mail_merge", "name": "Mail Merge", "enabled": True},
        {"key": "crew_hours", "name": "Crew Hours", "enabled": True},
    ]

# ---------------------------------------------
# App Init
# ---------------------------------------------
@app.on_event("startup")
def startup_db_seed():
    db = next(get_db())
    # Create a default user if none exists
    if not db.query(User).first():
        from .auth import get_password_hash
        admin = User(email="admin@redsea.com", hashed_password=get_password_hash("password"), full_name="Local Admin")
        db.add(admin)
        db.commit()
        db.refresh(admin)
        role = UserRole(user_id=admin.id, role=AppRole.super_admin)
        db.add(role)
        db.commit()
        print("Created default user: admin@redsea.com / password")
        
    # Seed default modules
    default_modules = [
        {"key": "task_extractor", "name": "Task Extractor", "category": "PDF Processing", "enabled": True},
        {"key": "task_stamping", "name": "Task Stamping", "category": "PDF Processing", "enabled": True},
        {"key": "effectivity", "name": "Effectivity / TCM", "category": "Aviation", "enabled": True},
        {"key": "check_control", "name": "Check Control", "category": "Quality", "enabled": True},
        {"key": "utilization", "name": "Utilization", "category": "Analytics", "enabled": True},
        {"key": "cmp_tcm", "name": "CMP / TCM", "category": "Compliance", "enabled": True},
        {"key": "cover_merge", "name": "Cover Merge", "category": "Documents", "enabled": True},
        {"key": "mail_merge", "name": "Mail Merge", "category": "Documents", "enabled": True},
        {"key": "crew_hours", "name": "Crew Hours", "category": "Statistics", "enabled": True},
    ]
    
    for mod in default_modules:
        if not db.query(Module).filter(Module.key == mod["key"]).first():
            db.add(Module(**mod))
    db.commit()
