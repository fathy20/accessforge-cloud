"""Seed a minimal, clearly-synthetic dataset for local frontend development.

Creates: one user per role (all with the same well-known dev password),
two projects, a handful of jobs in different states, and a few notifications.
Everything is prefixed ``dev-`` / ``DEV`` and uses ``@dev.local`` addresses so
it can never be mistaken for production data. No real crew names, person
codes, or flights: flight/crew data is not stored in this database at all —
it comes live from LEON, and the Crew Hours module simply reports LEON as
unconfigured on a machine without credentials.

Safety: refuses to run unless APP_ENV is development/test AND the configured
database is SQLite. It can never touch SQL Server.

Idempotent: re-running detects the marker account and exits without changes.

Usage:
    python -m backend.tools.seed_dev_data
"""

from __future__ import annotations

import sys

from backend.auth import get_password_hash
from backend.config import get_app_env
from backend.database import SessionLocal, engine
from backend.models import (
    AppRole,
    Job,
    JobStatus,
    Notification,
    Project,
    User,
    UserRole,
    UserStatus,
)
from backend.tools.sync_registry import sync_registry

EXIT_SUCCESS = 0
EXIT_REFUSED = 1
EXIT_ERROR = 3

# Deliberately public: local development only. The seed refuses to run against
# anything but a local SQLite development/test database.
DEV_PASSWORD = "dev-local-password-123"

SEED_USERS = (
    ("dev-admin@dev.local", "Dev Admin", AppRole.admin),
    ("dev-engineer@dev.local", "Dev Engineer", AppRole.engineer),
    ("dev-viewer@dev.local", "Dev Viewer", AppRole.viewer),
    ("dev-guest@dev.local", "Dev Guest", AppRole.guest),
)
MARKER_EMAIL = SEED_USERS[0][0]


def seed() -> int:
    app_env = get_app_env()
    dialect = getattr(getattr(engine, "dialect", None), "name", "unknown")
    if app_env not in ("development", "test") or dialect != "sqlite":
        print(
            f"Refusing to seed: APP_ENV={app_env!r}, dialect={dialect!r}. "
            "This tool only seeds a local SQLite development database.",
            file=sys.stderr,
        )
        return EXIT_REFUSED

    with SessionLocal() as db:
        if db.query(User).filter(User.email == MARKER_EMAIL).first():
            print("Seed data already present; nothing to do.")
            return EXIT_SUCCESS

        # Modules/permissions projection first, so seeded roles resolve grants.
        sync_registry(db)

        hashed = get_password_hash(DEV_PASSWORD)
        users: dict[str, User] = {}
        for email, full_name, role in SEED_USERS:
            user = User(
                email=email,
                full_name=full_name,
                hashed_password=hashed,
                status=UserStatus.active,
            )
            db.add(user)
            db.flush()
            db.add(UserRole(user_id=user.id, role=role))
            users[email] = user

        engineer = users["dev-engineer@dev.local"]
        admin = users["dev-admin@dev.local"]

        db.add_all(
            [
                Project(
                    owner_id=engineer.id,
                    name="DEV Line Check A6-FAKE",
                    code="DEV-001",
                    tail_number="A6-FAKE",
                    station="DEV",
                    description="Synthetic project for local development.",
                ),
                Project(
                    owner_id=admin.id,
                    name="DEV Cabin Refit ZZ-TEST",
                    code="DEV-002",
                    tail_number="ZZ-TEST",
                    station="DEV",
                    description="Second synthetic project.",
                ),
            ]
        )

        db.add_all(
            [
                Job(
                    user_id=engineer.id,
                    module_key="check_control",
                    status=JobStatus.done,
                    input_refs={"files": [], "data_source": "files"},
                    output_refs={"files": []},
                    progress=100,
                ),
                Job(
                    user_id=engineer.id,
                    module_key="task_extractor",
                    status=JobStatus.failed,
                    input_refs={"files": [], "data_source": "files"},
                    error_message="DEV seed: synthetic failure for UI states.",
                    progress=40,
                ),
                Job(
                    user_id=engineer.id,
                    module_key="mail_merge",
                    status=JobStatus.queued,
                    input_refs={"files": [], "data_source": "files"},
                ),
            ]
        )

        db.add_all(
            [
                Notification(
                    user_id=engineer.id,
                    kind="job",
                    title="DEV: job finished",
                    body="Synthetic notification for the bell UI.",
                ),
                Notification(
                    user_id=admin.id,
                    kind="system",
                    title="DEV: welcome",
                    body="Synthetic notification for the admin account.",
                ),
            ]
        )

        db.commit()

    print(
        "Seeded: 4 users (admin/engineer/viewer/guest @dev.local, password "
        f"{DEV_PASSWORD!r}), 2 projects, 3 jobs, 2 notifications."
    )
    print("Note: no flights/crew rows exist in this database by design — that "
          "data comes live from LEON and is absent locally.")
    return EXIT_SUCCESS


if __name__ == "__main__":
    raise SystemExit(seed())
