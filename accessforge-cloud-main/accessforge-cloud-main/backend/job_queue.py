"""SQL-backed job queue primitives shared by the API and the worker.

There is no broker: the ``jobs`` table is the queue. Correctness rests on one
idea — every state transition is an optimistic UPDATE whose WHERE clause
names the state it expects, and the caller checks the row count:

* a claim is ``WHERE id = :id AND (status = queued OR (status = running AND
  lease_expires_at <= now))`` and stamps a fresh ``lease_token``;
* every later write by that worker is ``WHERE id = :id AND lease_token =
  :token``.

A worker whose lease expired and was reclaimed therefore cannot overwrite the
row the newer attempt owns, no matter how late its writes arrive. The
guarantee is at-least-once: a job whose worker died mid-run is executed again
by the reclaimer, so handlers must tolerate re-execution.

Both dialects the project targets (SQLite for development, SQL Server for
production) execute a single-row UPDATE atomically, which is all the claim
needs. Under heavy contention SQL Server hints (READPAST/READCOMMITTEDLOCK)
would reduce retries; they are a tuning knob, not a correctness requirement,
and are deliberately not used because they cannot be exercised here.
"""

from __future__ import annotations

import os
import socket
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import and_, or_, update
from sqlalchemy.orm import Session

from .models import Job, JobStatus


def _int_setting(name: str, default: int, minimum: int = 1) -> int:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if value < minimum:
        raise ValueError(f"{name} must be >= {minimum}")
    return value


# How long a claim is valid without a heartbeat before another worker may
# reclaim the job. Must comfortably exceed HEARTBEAT_SECONDS.
LEASE_SECONDS = _int_setting("JOB_LEASE_SECONDS", 120)
HEARTBEAT_SECONDS = _int_setting("JOB_HEARTBEAT_SECONDS", 30)
# Wall-clock cap per attempt; the child process is killed past it.
TIMEOUT_SECONDS = _int_setting("JOB_TIMEOUT_SECONDS", 3600)
# Claims (first run + reclaims) before a job whose workers keep dying is
# marked failed instead of being retried forever.
MAX_ATTEMPTS = _int_setting("JOB_MAX_ATTEMPTS", 3)
POLL_SECONDS = float(os.environ.get("JOB_POLL_SECONDS", "2"))

ACTIVE_STATUSES = (JobStatus.queued, JobStatus.running)
TERMINAL_STATUSES = (JobStatus.done, JobStatus.failed, JobStatus.cancelled)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(value: datetime | None) -> datetime | None:
    """SQLite hands back naive datetimes for timezone-aware columns; they were
    written as UTC, so treat them as such."""
    if value is None:
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def default_worker_id() -> str:
    return f"{socket.gethostname()}:{os.getpid()}"


@dataclass(frozen=True)
class Claim:
    job_id: str
    lease_token: str
    attempt: int
    module_key: str
    user_id: str


def _claimable(now: datetime):
    return or_(
        Job.status == JobStatus.queued,
        and_(
            Job.status == JobStatus.running,
            Job.lease_expires_at.isnot(None),
            Job.lease_expires_at <= now,
        ),
    )


def claim_next_job(
    db: Session,
    worker_id: str,
    *,
    lease_seconds: int = LEASE_SECONDS,
    max_attempts: int = MAX_ATTEMPTS,
    scan_limit: int = 20,
) -> Claim | None:
    """Atomically take ownership of the oldest claimable job, or return None.

    Candidates are read first, then each is claimed with a conditional UPDATE;
    a row another worker took in between yields rowcount 0 and is skipped. A
    reclaim of a job that already reached ``max_attempts`` marks it failed
    instead of running it again.
    """

    now = utcnow()
    candidates = (
        db.query(Job)
        .filter(_claimable(now))
        .order_by(Job.created_at, Job.id)
        .limit(scan_limit)
        .all()
    )

    for candidate in candidates:
        if candidate.status == JobStatus.running and (candidate.attempt or 0) >= max_attempts:
            db.execute(
                update(Job)
                .where(Job.id == candidate.id, _claimable(now))
                .values(
                    status=JobStatus.failed,
                    error_message=(
                        f"Worker lease expired after {candidate.attempt} attempt(s); "
                        "the job was not retried again."
                    ),
                    completed_at=now,
                    lease_token=None,
                    lease_expires_at=None,
                )
                .execution_options(synchronize_session=False)
            )
            db.commit()
            continue

        token = str(uuid.uuid4())
        result = db.execute(
            update(Job)
            .where(Job.id == candidate.id, _claimable(now))
            .values(
                status=JobStatus.running,
                lease_owner=worker_id,
                lease_token=token,
                lease_expires_at=now + timedelta(seconds=lease_seconds),
                heartbeat_at=now,
                started_at=now,
                attempt=Job.attempt + 1,
                progress=0,
            )
            .execution_options(synchronize_session=False)
        )
        db.commit()
        if result.rowcount == 1:
            db.expire_all()
            attempt = db.query(Job.attempt).filter(Job.id == candidate.id).scalar() or 0
            return Claim(
                job_id=str(candidate.id),
                lease_token=token,
                attempt=int(attempt),
                module_key=candidate.module_key,
                user_id=str(candidate.user_id),
            )

    return None


def fenced_update(db: Session, job_id: str, token: str, **values: Any) -> bool:
    """Apply ``values`` only if the row is still leased under ``token``.

    Returns False when the lease was lost (reclaimed, cancelled, or finished
    by someone else); the caller must then stop writing. (``values`` may
    itself set ``lease_token``, which is why the parameter is named ``token``.)
    """

    result = db.execute(
        update(Job)
        .where(Job.id == job_id, Job.lease_token == token)
        .values(**values)
        .execution_options(synchronize_session=False)
    )
    db.commit()
    return result.rowcount == 1


def extend_lease(
    db: Session,
    job_id: str,
    lease_token: str,
    *,
    lease_seconds: int = LEASE_SECONDS,
) -> bool:
    now = utcnow()
    return fenced_update(
        db,
        job_id,
        lease_token,
        lease_expires_at=now + timedelta(seconds=lease_seconds),
        heartbeat_at=now,
    )


def finish(
    db: Session,
    job_id: str,
    lease_token: str,
    status: JobStatus,
    **values: Any,
) -> bool:
    """Terminal write. Clears the token so no later fenced write can land."""

    return fenced_update(
        db,
        job_id,
        lease_token,
        status=status,
        completed_at=utcnow(),
        lease_token=None,
        lease_expires_at=None,
        **values,
    )


def release_for_requeue(db: Session, job_id: str, lease_token: str) -> bool:
    """Give a claimed job back to the queue (graceful worker shutdown)."""

    return fenced_update(
        db,
        job_id,
        lease_token,
        status=JobStatus.queued,
        lease_token=None,
        lease_expires_at=None,
        heartbeat_at=None,
        started_at=None,
        progress=0,
    )


def is_cancel_requested(db: Session, job_id: str) -> bool:
    return bool(db.query(Job.cancel_requested).filter(Job.id == job_id).scalar())


def request_cancel(job: Job) -> str:
    """Cancel semantics shared by the API: queued jobs stop immediately, a
    running job is flagged for the worker to kill, terminal jobs are left
    alone. Returns what happened; the caller commits."""

    if job.status == JobStatus.queued:
        job.status = JobStatus.cancelled
        job.completed_at = utcnow()
        job.lease_token = None
        job.lease_expires_at = None
        return "cancelled"
    if job.status == JobStatus.running:
        job.cancel_requested = True
        return "cancel_requested"
    return "noop"


def requeue_for_retry(job: Job) -> None:
    """Put a failed or cancelled job back at the end of the queue."""

    job.status = JobStatus.queued
    job.error_message = None
    job.progress = 0
    job.output_refs = {}
    job.started_at = None
    job.completed_at = None
    job.cancel_requested = False
    job.lease_owner = None
    job.lease_token = None
    job.lease_expires_at = None
    job.heartbeat_at = None
