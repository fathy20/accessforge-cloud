import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel
from sqlalchemy.orm import Session
from passlib.context import CryptContext
import jwt
import time
from collections import defaultdict

from .database import get_db
from .config import SELF_SIGNUP_ENABLED
from .models import User, UserStatus
from .rbac.permissions import record_audit

class LoginRequest(BaseModel):
    email: str
    password: str

class RegisterRequest(BaseModel):
    email: str
    password: str
    full_name: Optional[str] = "User"

# Authentication config
MIN_JWT_SECRET_KEY_LENGTH = 32
SECRET_KEY = os.getenv("JWT_SECRET_KEY")
if not SECRET_KEY:
    raise ValueError("JWT_SECRET_KEY environment variable is required")
if len(SECRET_KEY) < MIN_JWT_SECRET_KEY_LENGTH:
    raise ValueError("JWT_SECRET_KEY must be at least 32 characters long")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7 # 7 days

# One password policy for every path that sets a password. The registration
# route previously accepted any length while change-password demanded 12, so
# the rule a user hit depended on which form they used.
MIN_PASSWORD_LENGTH = 12
MAX_PASSWORD_LENGTH = 72  # bcrypt only reads 72 bytes; longer would silently truncate.

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/auth/login")

# Verified against a random throwaway password below when the email is unknown,
# so a login probe costs one bcrypt either way and response timing does not
# reveal whether an account exists.
_TIMING_EQUALIZATION_HASH = pwd_context.hash(secrets.token_urlsafe(24))

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)


def validate_new_password(password: str) -> str | None:
    """Return the policy violation for a candidate password, or None if it passes."""

    if len(password) < MIN_PASSWORD_LENGTH:
        return f"Password must be at least {MIN_PASSWORD_LENGTH} characters long"
    if len(password.encode("utf-8")) > MAX_PASSWORD_LENGTH:
        return f"Password must be at most {MAX_PASSWORD_LENGTH} bytes long"
    return None


def _password_stamp(user: User) -> str:
    """A value that changes exactly when the user's password changes.

    Embedded in every token and checked on every request, it revokes all
    outstanding sessions the moment a password is changed or reset.
    """

    changed_at = user.password_changed_at
    return changed_at.isoformat() if changed_at is not None else ""

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def issue_user_token(user: User) -> str:
    return create_access_token(
        data={"sub": str(user.id), "pwd": _password_stamp(user)},
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    )

async def _get_current_user_for_statuses(
    token: str,
    db: Session,
    allowed_statuses: set[UserStatus],
):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except jwt.PyJWTError:
        raise credentials_exception

    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise credentials_exception
    # A token minted before the user's latest password change is dead: this is
    # what makes an admin reset or a password change revoke stolen sessions.
    if payload.get("pwd") != _password_stamp(user):
        raise credentials_exception
    if user.status not in allowed_statuses:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is not active")
    return user


async def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    return await _get_current_user_for_statuses(token, db, {UserStatus.active})


async def get_current_user_password_change_allowed(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
):
    return await _get_current_user_for_statuses(
        token,
        db,
        {UserStatus.active, UserStatus.password_change_required},
    )

router = APIRouter(prefix="/api/auth", tags=["auth"])

_login_attempts: dict[str, list[float]] = defaultdict(list)
MAX_ATTEMPTS = 5
MAX_FAILED_LOGINS = 5
WINDOW_SECONDS = 300  # 5 minutes
# The limiter map is keyed by client-supplied emails, so without a bound an
# attacker cycling random addresses grows it forever. Past this size, expired
# windows are swept before admitting a new key.
MAX_TRACKED_LOGIN_KEYS = 10_000


def _prune_expired_attempts(now: float) -> None:
    for key in [k for k, stamps in _login_attempts.items() if all(now - t >= WINDOW_SECONDS for t in stamps)]:
        _login_attempts.pop(key, None)


def _check_rate_limit(email: str):
    now = time.time()
    if email not in _login_attempts and len(_login_attempts) >= MAX_TRACKED_LOGIN_KEYS:
        _prune_expired_attempts(now)
    attempts = _login_attempts[email]
    _login_attempts[email] = [t for t in attempts if now - t < WINDOW_SECONDS]
    if len(_login_attempts[email]) >= MAX_ATTEMPTS:
        raise HTTPException(status_code=429, detail="Too many login attempts. Try again in 5 minutes.")
    _login_attempts[email].append(now)


def reset_login_rate_limit(email: str) -> None:
    _login_attempts.pop(email, None)


def generate_temporary_password() -> tuple[str, str]:
    temporary_password = secrets.token_urlsafe(24)
    return temporary_password, get_password_hash(temporary_password)

@router.post("/login")
def login_for_access_token(data: LoginRequest, db: Session = Depends(get_db)):
    _check_rate_limit(data.email)
    user = db.query(User).filter(User.email == data.email).first()
    if user is None:
        # Unknown email: burn the same bcrypt cost as a real check so response
        # timing does not disclose which addresses have accounts.
        verify_password(data.password, _TIMING_EQUALIZATION_HASH)
        credentials_valid = False
    else:
        credentials_valid = verify_password(data.password, user.hashed_password)
    if not credentials_valid:
        record_audit(
            db,
            None,
            "login_failure",
            "user",
            user.id if user is not None else None,
            reason="invalid_credentials",
        )
        if user is not None and user.status in {
            UserStatus.active,
            UserStatus.password_change_required,
        }:
            user.failed_login_count = (user.failed_login_count or 0) + 1
            if user.failed_login_count >= MAX_FAILED_LOGINS:
                user.status = UserStatus.locked
                user.locked_at = datetime.now(timezone.utc)
                record_audit(db, user, "account_locked", "user", user.id)
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if user.status not in {UserStatus.active, UserStatus.password_change_required}:
        record_audit(
            db,
            user,
            "login_failure",
            "user",
            user.id,
            reason="inactive_account",
            status=user.status,
        )
        db.commit()
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is not active")

    user.failed_login_count = 0
    user.locked_at = None
    user.last_login_at = datetime.now(timezone.utc)
    record_audit(db, user, "login_success", "user", user.id)
    db.commit()

    return {
        "access_token": issue_user_token(user),
        "token_type": "bearer",
        "must_change_password": user.status == UserStatus.password_change_required,
    }

@router.post("/register", status_code=status.HTTP_202_ACCEPTED)
def register_user(data: RegisterRequest, db: Session = Depends(get_db)):
    if not SELF_SIGNUP_ENABLED:
        raise HTTPException(status_code=403, detail="Self-signup is disabled")

    user = db.query(User).filter(User.email == data.email).first()
    if user:
        raise HTTPException(status_code=409, detail="Email already registered")

    policy_violation = validate_new_password(data.password)
    if policy_violation:
        raise HTTPException(status_code=400, detail=policy_violation)

    hashed_password = get_password_hash(data.password)
    user = User(
        email=data.email,
        hashed_password=hashed_password,
        full_name=data.full_name or "User",
        status=UserStatus.pending_approval,
    )
    db.add(user)
    db.flush()
    record_audit(db, user, "signup", "user", user.id)
    db.commit()
    return {
        "status": UserStatus.pending_approval.value,
        "message": "Registration request is pending approval.",
    }


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


@router.post("/change-password")
def change_password(
    data: ChangePasswordRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_password_change_allowed),
):
    if not verify_password(data.current_password, current_user.hashed_password):
        record_audit(
            db,
            current_user,
            "password_change_failure",
            "user",
            current_user.id,
            reason="current_password_incorrect",
        )
        db.commit()
        raise HTTPException(status_code=400, detail="Current password is incorrect")

    policy_violation = validate_new_password(data.new_password)
    if policy_violation:
        record_audit(
            db,
            current_user,
            "password_change_failure",
            "user",
            current_user.id,
            reason="password_policy",
        )
        db.commit()
        raise HTTPException(status_code=400, detail=policy_violation)

    if data.new_password == data.current_password:
        record_audit(
            db,
            current_user,
            "password_change_failure",
            "user",
            current_user.id,
            reason="password_unchanged",
        )
        db.commit()
        raise HTTPException(status_code=400, detail="New password must differ from the current password")

    current_user.hashed_password = get_password_hash(data.new_password)
    current_user.password_changed_at = datetime.now(timezone.utc)
    current_user.failed_login_count = 0
    if current_user.status == UserStatus.password_change_required:
        current_user.status = UserStatus.active
    record_audit(db, current_user, "password_change", "user", current_user.id)
    db.commit()
    db.refresh(current_user)
    # The stamp change just revoked every outstanding token, including the one
    # authorizing this request — hand back a live replacement so the client
    # continues without a re-login.
    return {
        "status": "success",
        "access_token": issue_user_token(current_user),
        "token_type": "bearer",
    }

@router.get("/me")
def read_users_me(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    roles = [r.role.value for r in current_user.roles]
    return {
        "id": current_user.id,
        "email": current_user.email,
        "full_name": current_user.full_name,
        "roles": roles,
        # The profile page renders these; without them every field shows empty.
        "department": current_user.department,
        "job_title": current_user.job_title,
        "phone": current_user.phone,
        "employee_id": current_user.employee_id,
        "avatar_url": current_user.avatar_url,
        "status": current_user.status.value if hasattr(current_user.status, "value") else current_user.status,
    }


class ProfileUpdate(BaseModel):
    full_name: Optional[str] = None
    department: Optional[str] = None
    job_title: Optional[str] = None
    phone: Optional[str] = None
    employee_id: Optional[str] = None
    avatar_url: Optional[str] = None


_PROFILE_FIELD_LIMITS = {
    "full_name": 255,
    "department": 255,
    "job_title": 255,
    "phone": 64,
    "employee_id": 64,
    "avatar_url": 512,
}


@router.put("/profile")
def update_profile(
    data: ProfileUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Self-service profile update; the UI has always called this route."""

    provided = data.model_dump(exclude_unset=True)
    changed_fields = []
    for field, value in provided.items():
        if value is not None:
            value = value.strip()
            if len(value) > _PROFILE_FIELD_LIMITS[field]:
                raise HTTPException(
                    status_code=400,
                    detail=f"{field} must be at most {_PROFILE_FIELD_LIMITS[field]} characters",
                )
            value = value or None
        if getattr(current_user, field) != value:
            setattr(current_user, field, value)
            changed_fields.append(field)

    if changed_fields:
        # Field names only: phone numbers and employee ids stay out of the log.
        record_audit(
            db,
            current_user,
            "profile_update",
            "user",
            current_user.id,
            fields=sorted(changed_fields),
        )
        db.commit()
    return {"status": "success", "updated": sorted(changed_fields)}
