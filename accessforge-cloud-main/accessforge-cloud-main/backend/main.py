import os
import shutil
from pathlib import Path
from typing import List

from fastapi import FastAPI, UploadFile, File, Depends, BackgroundTasks, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from pydantic import BaseModel
import traceback
import json

from .database import engine, Base, get_db
from .models import User, UserRole, AppRole, Upload, Job, JobStatus, UploadKind, Module
from .auth import router as auth_router, get_current_user

# Create database tables
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Redsea Local Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)

UPLOAD_DIR = Path("local_storage/uploads")
OUTPUT_DIR = Path("local_storage/outputs")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------
# Uploads API
# ---------------------------------------------
@app.post("/api/uploads")
async def upload_files(
    files: List[UploadFile] = File(...), 
    db: Session = Depends(get_db), 
    current_user: User = Depends(get_current_user)
):
    results = []
    for file in files:
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
            shutil.copyfileobj(file.file, buffer)
            
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

import tempfile
import traceback
import sys

def run_job_background(job_id: str):
    db = next(get_db())
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        return
        
    job.status = JobStatus.running
    db.commit()
    
    def log_progress(progress: int, msg: str):
        # We need a new session to avoid concurrent issues if it runs long
        _db = next(get_db())
        _j = _db.query(Job).filter(Job.id == job_id).first()
        if _j:
            _j.progress = progress
            _j.logs = list(_j.logs) + [{"level": progress, "msg": msg}]
            _db.commit()
            
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
                output_refs["files"].append({
                    "name": path.name,
                    "url": f"http://localhost:8000/api/downloads/{final_path.name}"
                })
                
        _db = next(get_db())
        _j = _db.query(Job).filter(Job.id == job_id).first()
        _j.status = JobStatus.done
        _j.progress = 100
        _j.output_refs = output_refs
        _db.commit()
        
    except Exception as e:
        _db = next(get_db())
        _j = _db.query(Job).filter(Job.id == job_id).first()
        _j.status = JobStatus.failed
        _j.error_message = str(e)
        _j.logs = list(_j.logs) + [{"level": 99, "msg": traceback.format_exc()}]
        _db.commit()

@app.post("/api/jobs")
def create_job(
    req: CreateJobRequest, 
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db), 
    current_user: User = Depends(get_current_user)
):
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
from fastapi.responses import FileResponse

@app.get("/api/downloads/{filename}")
def download_file(filename: str):
    file_path = OUTPUT_DIR / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(path=file_path, filename=filename.split("_", 2)[-1])

from typing import Optional

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
