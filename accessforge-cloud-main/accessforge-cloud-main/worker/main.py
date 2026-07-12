"""REDSEA worker — poll → run → callback loop.

  python -m worker.main

Required env:
  REDSEA_BASE_URL          https://project--<id>.lovable.app
  WORKER_HMAC_SECRET       shared with the web app
  SUPABASE_URL             your Supabase project URL
  SUPABASE_SERVICE_ROLE_KEY  service role key (worker-only)
Optional:
  WORKER_ID                default: "worker-1"
  POLL_IDLE_SECONDS        default: 3
"""
from __future__ import annotations
import os, sys, time, hmac, hashlib, json, traceback, logging
import requests

from .handlers import REGISTRY
from .storage import fetch_uploads, download_to, upload_output, make_workdir

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-7s %(message)s")
log = logging.getLogger("redsea.worker")

BASE   = os.environ["REDSEA_BASE_URL"].rstrip("/")
SECRET = os.environ["WORKER_HMAC_SECRET"].encode()
WID    = os.environ.get("WORKER_ID", "worker-1")
IDLE   = float(os.environ.get("POLL_IDLE_SECONDS", "3"))


def _sign(msg: bytes) -> str:
    return hmac.new(SECRET, msg, hashlib.sha256).hexdigest()


def poll():
    ts = str(int(time.time() * 1000))
    r = requests.post(
        f"{BASE}/api/public/hooks/worker-poll",
        headers={"x-worker-id": WID, "x-worker-ts": ts, "x-worker-sig": _sign(ts.encode())},
        timeout=20,
    )
    r.raise_for_status()
    return r.json().get("job")


def callback(payload: dict):
    raw = json.dumps(payload, separators=(",", ":")).encode()
    ts  = str(int(time.time() * 1000))
    sig = _sign(f"{ts}.".encode() + raw)
    r = requests.post(
        f"{BASE}/api/public/hooks/worker-callback",
        data=raw,
        headers={"content-type": "application/json", "x-worker-ts": ts, "x-worker-sig": sig},
        timeout=20,
    )
    r.raise_for_status()


def _mk_logger(job_id: str):
    def _log(progress: int, message: str):
        log.info(f"[{job_id[:8]}] {progress:3d}% {message}")
        try:
            callback({"jobId": job_id, "progress": max(1, min(99, int(progress))), "logMessage": message})
        except Exception as e:
            log.warning(f"callback failed: {e}")
    return _log


def run_job(job: dict) -> None:
    jid = job["id"]; mkey = job["module_key"]
    handler = REGISTRY.get(mkey)
    if not handler:
        callback({"jobId": jid, "status": "failed", "error": f"unknown module_key: {mkey}"}); return

    work = make_workdir(jid)
    log_progress = _mk_logger(jid)
    log_progress(2, f"start {mkey}")

    refs = job.get("input_refs") or {}
    upload_ids = refs.get("upload_ids") or []
    rows = fetch_uploads(upload_ids) if upload_ids else []
    inputs = download_to(rows, work / "in") if rows else []
    log_progress(8, f"downloaded {len(inputs)} input file(s)")

    out_paths = handler(job, inputs, work, log_progress)

    user_id = job.get("created_by") or "anonymous"
    storage_refs = [upload_output(p, jid, user_id) for p in out_paths]
    log_progress(99, f"uploaded {len(storage_refs)} output file(s)")

    callback({
        "jobId": jid, "status": "done", "progress": 100,
        "outputRefs": {"files": storage_refs},
        "logMessage": f"completed {mkey}",
    })


def main_loop():
    log.info(f"REDSEA worker {WID} polling {BASE}")
    while True:
        try:
            job = poll()
        except Exception as e:
            log.warning(f"poll error: {e}"); time.sleep(IDLE * 2); continue
        if not job:
            time.sleep(IDLE); continue
        log.info(f"claimed job {job['id']}  module={job['module_key']}")
        try:
            run_job(job)
        except Exception as e:
            log.exception("job failed")
            try:
                callback({"jobId": job["id"], "status": "failed", "error": f"{e}\n{traceback.format_exc()[:3500]}"})
            except Exception:
                pass


if __name__ == "__main__":
    try:
        main_loop()
    except KeyboardInterrupt:
        log.info("worker stopped"); sys.exit(0)
