"""Populate a local development database with disposable demo data.

The seeded accounts exist only in whatever local SQLite file this command is
pointed at. Nothing here runs from a migration or from application startup.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta, timezone
from typing import Sequence

from sqlalchemy.engine import make_url


EXIT_SUCCESS = 0
EXIT_REFUSED = 1
EXIT_ERROR = 3

SEED_EMAIL_DOMAIN = "dev.local"
SEED_PASSWORD = "devpassword123"

# Dialects that can only mean a shared or remote server. Checked as substrings
# before the URL is parsed so a malformed string cannot slip past the guard.
_NON_LOCAL_MARKERS = (
    "mssql",
    "pyodbc",
    "odbc_connect",
    "postgres",
    "mysql",
    "mariadb",
    "oracle",
    "snowflake",
    "sqlexpress",
)


class SeedSafetyError(RuntimeError):
    """Raised when the seed target is anything other than a local SQLite file."""


def assert_local_database(database_url: str | None, app_env: str = "development") -> str:
    """Return the URL only if it is a local SQLite target; otherwise raise.

    Pure: performs no I/O and opens no connection, so it can be called before
    ``backend.database`` is imported and an engine is built.
    """

    if app_env == "production":
        raise SeedSafetyError(
            "SEED SAFETY: refusing to seed demo data while APP_ENV is 'production'"
        )

    if database_url is None or not database_url.strip():
        raise SeedSafetyError("SEED SAFETY: DATABASE_URL is not configured")

    candidate = database_url.strip()
    lowered = candidate.casefold()

    for marker in _NON_LOCAL_MARKERS:
        if marker in lowered:
            raise SeedSafetyError(
                f"SEED SAFETY: DATABASE_URL targets a non-local backend ({marker!r})"
            )

    try:
        parsed = make_url(candidate)
        backend_name = parsed.get_backend_name()
    except Exception:
        raise SeedSafetyError(
            "SEED SAFETY: DATABASE_URL is not a valid SQLAlchemy URL"
        ) from None

    if backend_name != "sqlite":
        raise SeedSafetyError(
            f"SEED SAFETY: only a local SQLite database may be seeded; got {backend_name!r}"
        )

    if parsed.host:
        raise SeedSafetyError("SEED SAFETY: a local SQLite URL must not name a host")

    if parsed.username or parsed.password:
        raise SeedSafetyError("SEED SAFETY: a local SQLite URL must not carry credentials")

    # make_url collapses the UNC prefix in "sqlite:///\\host\share" down to a single
    # backslash, so the raw string is inspected as well as the parsed path.
    database_path = parsed.database or ""
    if (
        "\\\\" in candidate
        or database_path.startswith("\\")
        or database_path.startswith("//")
    ):
        raise SeedSafetyError("SEED SAFETY: SQLite path must not be a network share")

    return candidate


def _seed_accounts() -> tuple[tuple[str, str, str], ...]:
    """(email, full name, role) for each demo account."""

    return (
        (f"dev-admin@{SEED_EMAIL_DOMAIN}", "Dev Admin", "admin"),
        (f"dev-engineer@{SEED_EMAIL_DOMAIN}", "Dev Engineer", "engineer"),
        (f"dev-viewer@{SEED_EMAIL_DOMAIN}", "Dev Viewer", "viewer"),
        (f"dev-guest@{SEED_EMAIL_DOMAIN}", "Dev Guest", "guest"),
    )


# The dashboard scopes every query to the signed-in user (Job.user_id ==
# current_user.id), so activity seeded onto one account is invisible from any
# other. This is factored out so it can be pointed at any existing account.
DEMO_JOBS = (
    ("done", 100, 1),
    ("done", 100, 3),
    ("running", 45, 0),
    ("queued", 0, 0),
    ("failed", 72, 5),
)

DEMO_NOTIFICATIONS = (
    ("job", "Task Extractor finished", "Your extraction job completed successfully.", "/jobs"),
    ("job", "Check Control failed", "A demo job failed so you can style the error state.", "/jobs"),
    ("system", "Welcome to REDSEA", "This is seeded demo data for local design work.", "/dashboard"),
)


def seed_activity_for(db, user, created: dict[str, int]) -> dict[str, int]:
    """Give one existing account demo jobs and notifications. Idempotent."""

    from datetime import datetime, timedelta, timezone

    from backend.models import Job, JobStatus, Module, Notification

    now = datetime.now(timezone.utc)
    module_keys = [k for (k,) in db.query(Module.key).order_by(Module.sort_order).all()]
    if not module_keys:
        return created

    if db.query(Job).filter(Job.user_id == user.id).first() is None:
        for index, (status, progress, days_ago) in enumerate(DEMO_JOBS):
            completed = status in {"done", "failed"}
            db.add(
                Job(
                    user_id=user.id,
                    module_key=module_keys[index % len(module_keys)],
                    status=JobStatus(status),
                    progress=progress,
                    input_refs={"files": [], "data_source": "demo"},
                    output_refs={"files": []},
                    logs=[{"level": progress, "msg": f"demo job seeded ({status})"}],
                    error_message="Demo failure for layout testing." if status == "failed" else None,
                    created_at=now - timedelta(days=days_ago, hours=index),
                    started_at=now - timedelta(days=days_ago, hours=index),
                    completed_at=now - timedelta(days=days_ago) if completed else None,
                )
            )
            created["jobs"] += 1

    for kind, title, body, link in DEMO_NOTIFICATIONS:
        exists = (
            db.query(Notification)
            .filter(Notification.user_id == user.id, Notification.title == title)
            .first()
        )
        if exists is None:
            db.add(
                Notification(
                    user_id=user.id,
                    kind=kind,
                    title=title,
                    body=body,
                    link=link,
                    created_at=now - timedelta(hours=len(title) % 12),
                )
            )
            created["notifications"] += 1

    db.commit()
    return created


def refresh_demo_dates(db) -> dict[str, int]:
    """Re-stamp seeded jobs relative to now.

    Seeded rows carry absolute timestamps, so demo data silently falls out of
    the dashboard's rolling 14-day window as real time passes and the chart
    goes blank while the row count still looks healthy. This pulls them back
    into range without touching real jobs — only rows this seeder created,
    identified by input_refs.data_source == "demo".
    """

    from datetime import datetime, timedelta, timezone

    from backend.models import Job

    now = datetime.now(timezone.utc)
    moved = 0
    for job in db.query(Job).all():
        refs = job.input_refs or {}
        if not isinstance(refs, dict) or refs.get("data_source") != "demo":
            continue
        index = moved % len(DEMO_JOBS)
        _status, _progress, days_ago = DEMO_JOBS[index]
        created = now - timedelta(days=days_ago, hours=index)
        job.created_at = created
        job.started_at = created
        if job.completed_at is not None:
            job.completed_at = now - timedelta(days=days_ago)
        moved += 1

    db.commit()
    return {"jobs_redated": moved}


def remove_seed_data(db) -> dict[str, int]:
    """Delete every row this seeder created, leaving real accounts untouched."""

    from backend.models import Job, Notification, Project, User, UserRole

    removed = {"users": 0, "projects": 0, "jobs": 0, "notifications": 0}
    suffix = f"@{SEED_EMAIL_DOMAIN}"

    # Demo activity can also have been attached to a REAL account via --for, so
    # clearing only the @dev.local users would leave that behind. Sweep every
    # job this seeder marked, whoever owns it, plus the notifications that came
    # with it. Real jobs carry no data_source marker and are untouched.
    for job in db.query(Job).all():
        refs = job.input_refs or {}
        if isinstance(refs, dict) and refs.get("data_source") == "demo":
            db.delete(job)
            removed["jobs"] += 1

    demo_titles = {title for _kind, title, _body, _link in DEMO_NOTIFICATIONS}
    for note in db.query(Notification).filter(Notification.title.in_(demo_titles)).all():
        db.delete(note)
        removed["notifications"] += 1

    db.flush()

    users = [u for u in db.query(User).all() if (u.email or "").endswith(suffix)]

    for user in users:
        removed["notifications"] += (
            db.query(Notification).filter(Notification.user_id == user.id).delete()
        )
        removed["jobs"] += db.query(Job).filter(Job.user_id == user.id).delete()
        removed["projects"] += db.query(Project).filter(Project.owner_id == user.id).delete()
        db.query(UserRole).filter(UserRole.user_id == user.id).delete()
        db.delete(user)
        removed["users"] += 1

    db.commit()
    return removed


def seed(db) -> dict[str, int]:
    """Insert demo accounts, projects, jobs and notifications. Idempotent."""

    from backend.auth import get_password_hash
    from backend.models import (
        AppRole,
        Job,
        JobStatus,
        Module,
        Notification,
        Project,
        User,
        UserRole,
        UserStatus,
    )

    now = datetime.now(timezone.utc)
    created = {"users": 0, "projects": 0, "jobs": 0, "notifications": 0}
    hashed = get_password_hash(SEED_PASSWORD)
    users: dict[str, User] = {}

    for email, full_name, role in _seed_accounts():
        user = db.query(User).filter(User.email == email).first()
        if user is None:
            user = User(
                email=email,
                full_name=full_name,
                hashed_password=hashed,
                status=UserStatus.active,
                department="Engineering",
                job_title=full_name,
            )
            db.add(user)
            db.flush()
            db.add(UserRole(user_id=user.id, role=AppRole(role)))
            created["users"] += 1
        users[role] = user

    db.flush()
    owner = users["admin"]

    demo_projects = (
        ("A320 Fleet Check Programme", "PRJ-A320", "Recurring check package for the A320 fleet."),
        ("B787 Cabin Retrofit", "PRJ-B787", "Cabin interior retrofit documentation workstream."),
    )
    for name, code, description in demo_projects:
        if db.query(Project).filter(Project.code == code).first() is None:
            db.add(
                Project(
                    owner_id=owner.id,
                    name=name,
                    code=code,
                    description=description,
                    status="active",
                )
            )
            created["projects"] += 1

    # Jobs reference modules.key, which application startup seeds via sync_registry.
    module_keys = [k for (k,) in db.query(Module.key).order_by(Module.sort_order).all()]
    if not module_keys:
        print(
            "Warning: no modules found. Start the backend once so sync_registry runs, "
            "then re-run this seeder to get demo jobs.",
            file=sys.stderr,
        )

    seed_activity_for(db, users["engineer"], created)

    db.commit()
    return created


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--for",
        dest="target_email",
        metavar="EMAIL",
        help=(
            "Give demo jobs and notifications to an EXISTING account instead of seeding "
            "the @dev.local set. The dashboard is scoped per user, so an account with no "
            "jobs of its own shows an empty dashboard however much other data exists."
        ),
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Re-date existing demo jobs relative to today, so they fall back inside "
             "the dashboard's rolling 14-day window.",
    )
    parser.add_argument(
        "--remove",
        action="store_true",
        help=f"Delete every @{SEED_EMAIL_DOMAIN} account and its rows instead of seeding.",
    )
    args = parser.parse_args(argv)

    # Resolve what the application itself would use. backend.config loads the
    # .env files and assembles a SQL Server URL from SQL_SERVER_* when those are
    # set, so guarding the resolved value catches targets the raw environment
    # variable alone would hide. Importing it builds no engine and opens no
    # connection.
    try:
        from backend.config import APP_ENV as resolved_env
        from backend.config import DATABASE_URL as resolved_url
    except Exception as exc:
        # A configuration that will not even resolve is never a safe seed target.
        print(f"SEED SAFETY: configuration refused this target ({exc})", file=sys.stderr)
        return EXIT_REFUSED

    try:
        url = assert_local_database(resolved_url, resolved_env)
    except SeedSafetyError as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_REFUSED

    from backend.database import SessionLocal

    db = SessionLocal()
    try:
        if args.refresh:
            counts = refresh_demo_dates(db)
            print(f"Refreshed demo dates on {url}: {counts}")
        elif args.target_email:
            from backend.models import User

            target = db.query(User).filter(User.email == args.target_email).first()
            if target is None:
                print(f"Error: no account with email {args.target_email!r}.", file=sys.stderr)
                return EXIT_ERROR
            counts = seed_activity_for(db, target, {"jobs": 0, "notifications": 0})
            print(f"Gave {args.target_email} demo activity on {url}: {counts}")
        elif args.remove:
            counts = remove_seed_data(db)
            print(f"Removed demo data from {url}: {counts}")
        else:
            counts = seed(db)
            print(f"Seeded {url}: {counts}")
            print(f"Sign in with any of the accounts below, password: {SEED_PASSWORD}")
            for email, _name, role in _seed_accounts():
                print(f"  {email:<32} {role}")
    except Exception as exc:
        db.rollback()
        print(f"Error: seeding failed ({type(exc).__name__}: {exc})", file=sys.stderr)
        return EXIT_ERROR
    finally:
        db.close()

    return EXIT_SUCCESS


if __name__ == "__main__":
    raise SystemExit(main())
