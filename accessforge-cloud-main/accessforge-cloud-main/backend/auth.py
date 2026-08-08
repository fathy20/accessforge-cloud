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

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/auth/login")

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

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

def _check_rate_limit(email: str):
    now = time.time()
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
    credentials_valid = bool(user and verify_password(data.password, user.hashed_password))
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

    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": str(user.id)}, expires_delta=access_token_expires
    )
    return {
        "access_token": access_token,
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

    if len(data.new_password) < 12:
        record_audit(
            db,
            current_user,
            "password_change_failure",
            "user",
            current_user.id,
            reason="password_too_short",
        )
        db.commit()
        raise HTTPException(status_code=400, detail="Password must be at least 12 characters long")

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
    return {"status": "success"}

@router.get("/me")
def read_users_me(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    roles = [r.role.value for r in current_user.roles]
    return {
        "id": current_user.id,
        "email": current_user.email,
        "full_name": current_user.full_name,
        "roles": roles
    }
