"""Standalone job worker: ``python -m worker.runner``.

Loop: claim the oldest queued (or expired-running) job with an optimistic
UPDATE, run it in a **child process**, and while the child runs:

* heartbeat — extend the lease every ``JOB_HEARTBEAT_SECONDS``; if the extend
  is rejected the lease was reclaimed, so kill the child and walk away
  without writing (the new owner's writes are the truth);
* cancellation — poll ``cancel_requested``; when set, kill the process tree
  and mark the job cancelled;
* timeout — past ``JOB_TIMEOUT_SECONDS`` kill the tree and mark it failed.

The child process is what makes a timeout real: cooperative flags cannot
interrupt a handler stuck inside OCR. On Windows ``terminate()`` neither runs
``finally`` blocks nor kills descendants (Tesseract), so the tree is killed
with ``taskkill /T``; on POSIX the child gets its own session and the whole
group receives SIGKILL.

Several workers may run at once: the claim is atomic, so a job is executed
by exactly one live lease at a time. Guarantee is at-least-once.
"""

from __future__ import annotations

import logging
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Sequence

from backend import job_queue
from backend.database import SessionLocal
from backend.models import JobStatus

logger = logging.getLogger("worker.runner")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CHILD_COMMAND: tuple[str, ...] = (sys.executable, "-m", "worker.job_child")


def kill_process_tree(process: subprocess.Popen) -> None:
    """Kill the child and everything it spawned, on both platforms."""

    if process.poll() is not None:
        return
    try:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                capture_output=True,
                check=False,
                timeout=30,
            )
        else:
            os.killpg(os.getpgid(process.pid), signal.SIGKILL)
    except Exception:  # noqa: BLE001 - best effort; fall through to terminate
        logger.exception("Process-tree kill failed; falling back to terminate().")
        process.terminate()
    try:
        process.wait(timeout=15)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=15)


class Worker:
    def __init__(
        self,
        worker_id: str | None = None,
        *,
        poll_seconds: float = job_queue.POLL_SECONDS,
        lease_seconds: int = job_queue.LEASE_SECONDS,
        heartbeat_seconds: float = job_queue.HEARTBEAT_SECONDS,
        timeout_seconds: float = job_queue.TIMEOUT_SECONDS,
        max_attempts: int = job_queue.MAX_ATTEMPTS,
        child_command: Sequence[str] = CHILD_COMMAND,
        tick_seconds: float = 1.0,
    ):
        self.worker_id = worker_id or job_queue.default_worker_id()
        self.poll_seconds = poll_seconds
        self.lease_seconds = lease_seconds
        self.heartbeat_seconds = heartbeat_seconds
        self.timeout_seconds = timeout_seconds
        self.max_attempts = max_attempts
        self.child_command = tuple(child_command)
        self.tick_seconds = tick_seconds
        self.stop_requested = False

    # -- lifecycle ---------------------------------------------------------

    def request_stop(self, *_args) -> None:
        logger.info("Stop requested; finishing the current job, claiming no more.")
        self.stop_requested = True

    def run_forever(self) -> None:
        for sig in (signal.SIGINT, signal.SIGTERM):
            signal.signal(sig, self.request_stop)
        logger.info("Worker %s started.", self.worker_id)
        while not self.stop_requested:
            if not self.run_once():
                time.sleep(self.poll_seconds)
        logger.info("Worker %s stopped.", self.worker_id)

    def run_once(self) -> bool:
        """Claim and run one job. Returns False when the queue was empty."""

        with SessionLocal() as db:
            claim = job_queue.claim_next_job(
                db,
                self.worker_id,
                lease_seconds=self.lease_seconds,
                max_attempts=self.max_attempts,
            )
        if claim is None:
            return False
        logger.info(
            "Claimed job %s (%s) attempt %d.", claim.job_id, claim.module_key, claim.attempt
        )
        self.run_claim(claim)
        return True

    # -- one job -----------------------------------------------------------

    def _spawn(self, claim: job_queue.Claim) -> subprocess.Popen:
        kwargs: dict = {"cwd": str(PROJECT_ROOT)}
        if os.name == "nt":
            kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            kwargs["start_new_session"] = True
        return subprocess.Popen([*self.child_command, claim.job_id, claim.lease_token], **kwargs)

    def run_claim(self, claim: job_queue.Claim) -> str:
        """Supervise one claimed job to a terminal outcome. Returns the outcome."""

        started = time.monotonic()
        last_heartbeat = started
        process = self._spawn(claim)

        while True:
            exit_code = process.poll()
            if exit_code is not None:
                return self._after_child_exit(claim, exit_code)

            now = time.monotonic()
            with SessionLocal() as db:
                if now - last_heartbeat >= self.heartbeat_seconds:
                    if not job_queue.extend_lease(
                        db, claim.job_id, claim.lease_token, lease_seconds=self.lease_seconds
                    ):
                        logger.warning("Lease for job %s was lost; killing child.", claim.job_id)
                        kill_process_tree(process)
                        return "lease_lost"
                    last_heartbeat = now

                if job_queue.is_cancel_requested(db, claim.job_id):
                    kill_process_tree(process)
                    job_queue.finish(
                        db, claim.job_id, claim.lease_token, JobStatus.cancelled, cancel_requested=False
                    )
                    logger.info("Job %s cancelled on request.", claim.job_id)
                    return "cancelled"

                if now - started >= self.timeout_seconds:
                    kill_process_tree(process)
                    job_queue.finish(
                        db,
                        claim.job_id,
                        claim.lease_token,
                        JobStatus.failed,
                        error_message=f"Job exceeded the {int(self.timeout_seconds)} s time limit and was stopped.",
                    )
                    logger.warning("Job %s timed out.", claim.job_id)
                    return "timeout"

                if self.stop_requested:
                    kill_process_tree(process)
                    job_queue.release_for_requeue(db, claim.job_id, claim.lease_token)
                    logger.info("Job %s released back to the queue for shutdown.", claim.job_id)
                    return "requeued"

            time.sleep(self.tick_seconds)

    def _after_child_exit(self, claim: job_queue.Claim, exit_code: int) -> str:
        # A child that completed properly already cleared the token with its
        # terminal write, so this fenced write is a no-op for it. It only
        # lands when the child died (crash, OOM, killed externally) while the
        # row still says running under our lease.
        with SessionLocal() as db:
            crashed = job_queue.finish(
                db,
                claim.job_id,
                claim.lease_token,
                JobStatus.failed,
                error_message=f"Worker child exited with code {exit_code} before completing the job.",
            )
        if crashed:
            logger.error("Job %s: child exited with %s before completing.", claim.job_id, exit_code)
            return "crashed"
        return "completed"


def main() -> None:
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    Worker().run_forever()


if __name__ == "__main__":
    main()
