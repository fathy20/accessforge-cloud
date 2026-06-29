"""Supabase Storage helpers — download inputs, upload outputs."""
from __future__ import annotations
import os, mimetypes, tempfile
from pathlib import Path
from typing import Iterable
from supabase import create_client, Client

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_SERVICE_ROLE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
UPLOADS_BUCKET = os.environ.get("UPLOADS_BUCKET", "uploads")
OUTPUTS_BUCKET = os.environ.get("OUTPUTS_BUCKET", "outputs")

_sb: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)


def fetch_uploads(upload_ids: Iterable[str]) -> list[dict]:
    res = _sb.table("uploads").select(
        "id, original_name, storage_path, kind, mime, metadata"
    ).in_("id", list(upload_ids)).execute()
    return res.data or []


def download_to(rows: list[dict], target_dir: str | Path) -> list[str]:
    target_dir = Path(target_dir); target_dir.mkdir(parents=True, exist_ok=True)
    paths: list[str] = []
    for r in rows:
        data = _sb.storage.from_(UPLOADS_BUCKET).download(r["storage_path"])
        p = target_dir / r["original_name"]
        p.write_bytes(data)
        paths.append(str(p))
    return paths


def upload_output(local_path: str, job_id: str, user_id: str, name: str | None = None) -> str:
    p = Path(local_path)
    name = name or p.name
    storage_path = f"{user_id}/{job_id}/{name}"
    mime, _ = mimetypes.guess_type(name)
    _sb.storage.from_(OUTPUTS_BUCKET).upload(
        storage_path, p.read_bytes(),
        {"contentType": mime or "application/octet-stream", "upsert": "true"},
    )
    return storage_path


def make_workdir(job_id: str) -> Path:
    base = Path(tempfile.gettempdir()) / "redsea-worker" / job_id
    (base / "in").mkdir(parents=True, exist_ok=True)
    (base / "out").mkdir(parents=True, exist_ok=True)
    return base
