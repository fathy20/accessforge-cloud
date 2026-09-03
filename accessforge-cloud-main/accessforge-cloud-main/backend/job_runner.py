"""Execute one job: resolve inputs, run the module handler, publish outputs.

Used two ways:

* **inline** (development, tests): the API schedules ``execute_job(job_id)``
  as a FastAPI BackgroundTask right after creating the row — the historical
  behaviour, kept so a single process is enough locally;
* **worker**: ``worker.job_child`` calls ``execute_job(job_id, lease_token)``
  in a killable child process. Every write then goes through the fenced
  update in :mod:`backend.job_queue`; if the lease was lost the child stops
  writing and exits, and the reclaiming worker's attempt owns the row.
"""

from __future__ import annotations

import logging
import os
import shutil
import tempfile
import traceback
from pathlib import Path
from typing import Any, Callable

from sqlalchemy import inspect as sa_inspect

from . import storage as storage_backend
from .database import SessionLocal
from .job_queue import fenced_update, utcnow
from .models import Job, JobStatus, Module, Upload, User
from .module_visibility import module_is_visible, module_visibility_inputs
from .rbac.permissions import record_audit

logger = logging.getLogger(__name__)

# Module-level so tests can patch the publish target the way they used to on
# backend.main (the runner lived there before the worker split).
OUTPUT_DIR = storage_backend.OUTPUT_DIR

# Bound the per-job log list: a chatty handler otherwise grows the JSON column
# (rewritten wholesale on every append) without limit.
MAX_JOB_LOG_ENTRIES = 200


class LeaseLost(RuntimeError):
    """The row is no longer leased to this attempt; stop touching it."""


def _append_job_log(logs, entry: dict) -> list:
    combined = list(logs or []) + [entry]
    return combined[-MAX_JOB_LOG_ENTRIES:]


def _changed_values(job: Job) -> dict[str, Any]:
    state = sa_inspect(job)
    return {
        attr.key: getattr(job, attr.key)
        for attr in state.attrs
        if attr.key in Job.__table__.columns and attr.history.has_changes()
    }


class _JobWriter:
    """Applies ``mutate(job)`` to the row.

    Inline mode commits the ORM change directly. Worker mode reads the row,
    lets ``mutate`` set attributes, then re-issues those attributes as one
    UPDATE fenced on the lease token, so a concurrent reclaim cannot be
    overwritten by a late write.
    """

    def __init__(self, job_id: str, lease_token: str | None):
        self.job_id = job_id
        self.lease_token = lease_token

    def write(self, mutate: Callable[[Job], None]) -> None:
        with SessionLocal() as db:
            job = db.query(Job).filter(Job.id == self.job_id).first()
            if job is None:
                raise LeaseLost("job row disappeared")
            if self.lease_token is not None and job.lease_token != self.lease_token:
                raise LeaseLost("lease token no longer matches")

            mutate(job)

            if self.lease_token is None:
                db.commit()
                return

            values = _changed_values(job)
            db.expunge(job)
            if values and not fenced_update(db, self.job_id, self.lease_token, **values):
                raise LeaseLost("fenced update rejected")


def _terminal(row: Job, status: JobStatus) -> None:
    row.status = status
    row.completed_at = utcnow()
    row.lease_token = None
    row.lease_expires_at = None


def execute_job(job_id: str, lease_token: str | None = None) -> None:
    writer = _JobWriter(job_id, lease_token)
    workdir: Path | None = None

    try:
        with SessionLocal() as db:
            job = db.query(Job).filter(Job.id == job_id).first()
            if job is None:
                return
            if lease_token is not None and job.lease_token != lease_token:
                logger.warning("Job lease already lost at start.", extra={"job_id": job_id})
                return
            cancel_requested = bool(job.cancel_requested)
            module_key = job.module_key
            user_id = job.user_id
            input_refs = dict(job.input_refs or {})

        if cancel_requested:
            writer.write(lambda row: _terminal(row, JobStatus.cancelled))
            return

        if lease_token is None:
            # Inline mode has no claim step; stamp the run here.
            def _start(row: Job) -> None:
                row.status = JobStatus.running
                row.started_at = utcnow()
                row.attempt = (row.attempt or 0) + 1
            writer.write(_start)

        def log_progress(progress: int, msg: str) -> None:
            def _log(row: Job) -> None:
                row.progress = progress
                row.logs = _append_job_log(row.logs, {"level": progress, "msg": msg})
            writer.write(_log)

        from worker.handlers import REGISTRY

        handler = REGISTRY.get(module_key)
        if not handler:
            raise ValueError(f"Module {module_key} not found in registry")

        with SessionLocal() as db:
            output_owner = db.query(User).filter(User.id == user_id).first()
            module = db.query(Module).filter(Module.key == module_key).first()
            if output_owner is None:
                module_permitted = False
            else:
                permissions, disabled_module_ids = module_visibility_inputs(db, output_owner)
                module_permitted = module_is_visible(module, permissions, disabled_module_ids)

            if not module_permitted:
                record_audit(db, output_owner, "job_module_denied", "job", job_id, module_key=module_key)
                db.commit()
                raise PermissionError("Module access denied")

            input_files: list[str] = []
            rejected_file_count = 0
            for fid in input_refs.get("files", []):
                upload = (
                    db.query(Upload)
                    .filter(Upload.id == fid, Upload.user_id == user_id)
                    .first()
                )
                if upload:
                    input_files.append(upload.storage_path)
                else:
                    rejected_file_count += 1

            if rejected_file_count:
                record_audit(
                    db,
                    output_owner,
                    "job_input_rejected",
                    "job",
                    job_id,
                    rejected_count=rejected_file_count,
                )
                db.commit()
                raise ValueError("One or more input files are unavailable to this job")

        if not input_files and input_refs.get("data_source") != "db":
            raise ValueError("No valid input files found for job")

        # Per-attempt workspace: a reclaimed job's second run must not collide
        # with files a dying first run left behind.
        workdir = (
            Path(tempfile.gettempdir()) / "redsea_backend" / f"{job_id}-{lease_token or 'inline'}"
        )
        (workdir / "in").mkdir(parents=True, exist_ok=True)
        (workdir / "out").mkdir(parents=True, exist_ok=True)

        log_progress(10, f"Starting module {module_key} with {len(input_files)} files")
        out_paths = handler({"id": str(job_id), "input_refs": input_refs}, input_files, workdir, log_progress)

        # Publish: persist artifacts, then describe them on the row in one
        # fenced write. A crash between the two leaves orphan files, never a
        # row pointing at files that do not exist (at-least-once, stated
        # honestly; TECHNICAL_DEBT #2 gives outputs a relational home).
        output_refs: dict[str, Any] = {"files": []}
        output_artifacts = []
        base_url = os.getenv("BASE_URL", "http://localhost:8000")
        for path_str in out_paths:
            try:
                artifact = storage_backend.persist_output_artifact(Path(path_str), OUTPUT_DIR)
            except FileNotFoundError:
                logger.warning("Generated output was not found.", extra={"job_id": job_id})
                continue
            output_artifacts.append(artifact)
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

        def _done(row: Job) -> None:
            _terminal(row, JobStatus.done)
            row.progress = 100
            row.output_refs = output_refs
        writer.write(_done)

        # Audit rows only once the publish landed; they are not fenced because
        # they describe files that now exist regardless of who owns the row.
        with SessionLocal() as db:
            owner = db.query(User).filter(User.id == user_id).first()
            for artifact in output_artifacts:
                record_audit(
                    db,
                    owner,
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
            db.commit()

    except LeaseLost as lost:
        # Another attempt owns the row now. Anything persisted above is an
        # orphan artifact at worst; the row is not ours to describe.
        logger.warning("Job lease lost; abandoning attempt: %s", lost, extra={"job_id": job_id})
    except Exception as exc:  # noqa: BLE001 - the failure is recorded on the row
        message = str(exc)[:2000]
        detail = traceback.format_exc()
        try:
            def _failed(row: Job) -> None:
                _terminal(row, JobStatus.failed)
                # The client-facing message is bounded; the full traceback
                # stays in the server-side logs column, which the API never
                # returns.
                row.error_message = message
                row.logs = _append_job_log(row.logs, {"level": 99, "msg": detail})
            writer.write(_failed)
        except LeaseLost:
            logger.warning("Job failed after its lease was lost.", extra={"job_id": job_id})
    finally:
        try:
            if workdir and workdir.exists():
                shutil.rmtree(workdir)
        except Exception:
            logger.exception("Failed to clean up job workspace.", extra={"job_id": job_id})


# Historical name: the inline BackgroundTasks path and older tests use it.
run_job_background = execute_job
