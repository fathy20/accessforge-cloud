"""Explicit operator command for creating the first super-admin account."""

from __future__ import annotations

import argparse
import getpass
import os
import sys
from typing import Sequence

from backend.auth import get_password_hash
from backend.database import SessionLocal
from backend.models import AppRole, User, UserRole


EXIT_SUCCESS = 0
EXIT_REFUSED = 1
EXIT_ERROR = 3
MIN_PASSWORD_LENGTH = 12


def _read_email(argument: str | None) -> str | None:
    value = argument if argument is not None else os.environ.get("BOOTSTRAP_ADMIN_EMAIL")
    if value is None or not value.strip():
        print(
            "Error: provide --email or set BOOTSTRAP_ADMIN_EMAIL.",
            file=sys.stderr,
        )
        return None
    return value.strip()


def _read_password() -> str | None:
    password = os.environ.get("BOOTSTRAP_ADMIN_PASSWORD")
    if password is not None:
        return password

    if not sys.stdin.isatty():
        print(
            "Error: BOOTSTRAP_ADMIN_PASSWORD is unset and no interactive TTY is available.",
            file=sys.stderr,
        )
        return None

    try:
        first = getpass.getpass("Bootstrap admin password: ")
        second = getpass.getpass("Confirm bootstrap admin password: ")
    except (EOFError, KeyboardInterrupt):
        print("Error: password entry was interrupted.", file=sys.stderr)
        return None

    if first != second:
        print("Error: password entries do not match.", file=sys.stderr)
        return None
    return first


def _create_super_admin(email: str, password: str) -> int:
    try:
        db = SessionLocal()
    except Exception:
        print("Error: could not open the configured database.", file=sys.stderr)
        return EXIT_ERROR

    try:
        if db.query(UserRole).filter(UserRole.role == AppRole.super_admin).first():
            print(
                "Refusing to bootstrap: a super admin already exists.",
                file=sys.stderr,
            )
            return EXIT_REFUSED

        if db.query(User).filter(User.email == email).first():
            print(
                f"Refusing to bootstrap: a user with email {email!r} already exists.",
                file=sys.stderr,
            )
            return EXIT_REFUSED

        admin = User(email=email, hashed_password=get_password_hash(password))
        db.add(admin)
        db.flush()
        db.add(UserRole(user_id=admin.id, role=AppRole.super_admin))
        db.commit()
    except Exception:
        db.rollback()
        print("Error: could not create the super admin; no account was created.", file=sys.stderr)
        return EXIT_ERROR
    finally:
        db.close()

    print(f"Created the first super admin for {email}.")
    return EXIT_SUCCESS


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create the first super-admin account.")
    parser.add_argument(
        "--email",
        help="Target email; otherwise BOOTSTRAP_ADMIN_EMAIL is used.",
    )
    args = parser.parse_args(argv)

    email = _read_email(args.email)
    if email is None:
        return EXIT_ERROR

    password = _read_password()
    if password is None:
        return EXIT_ERROR
    if len(password) < MIN_PASSWORD_LENGTH:
        print(
            f"Error: password must be at least {MIN_PASSWORD_LENGTH} characters long.",
            file=sys.stderr,
        )
        return EXIT_ERROR

    return _create_super_admin(email, password)


if __name__ == "__main__":
    raise SystemExit(main())
