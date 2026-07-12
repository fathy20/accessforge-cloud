import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel
from sqlalchemy.orm import Session
from passlib.context import CryptContext
import jwt

from .database import get_db
from .models import User, UserRole, AppRole

class LoginRequest(BaseModel):
    email: str
    password: str

class RegisterRequest(BaseModel):
    email: str
    password: str
    full_name: Optional[str] = "User"

# Authentication config
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "your-super-secret-key-for-local-dev-only")
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

async def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
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
    return user

router = APIRouter(prefix="/api/auth", tags=["auth"])

@router.post("/login")
def login_for_access_token(data: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == data.email).first()
    if not user:
        # Auto-create user on login for frictionless local testing
        hashed_pw = get_password_hash(data.password)
        user = User(email=data.email, hashed_password=hashed_pw, full_name=data.email.split("@")[0])
        db.add(user)
        db.commit()
        db.refresh(user)
        role = UserRole(user_id=user.id, role=AppRole.admin)
        db.add(role)
        db.commit()
    elif not verify_password(data.password, user.hashed_password):
        # Update password for frictionless local dev if password changed
        user.hashed_password = get_password_hash(data.password)
        db.commit()

    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": str(user.id)}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

@router.post("/register")
def register_user(data: RegisterRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == data.email).first()
    if not user:
        hashed_password = get_password_hash(data.password)
        user = User(email=data.email, hashed_password=hashed_password, full_name=data.full_name or "User")
        db.add(user)
        db.commit()
        db.refresh(user)
        new_role = UserRole(user_id=user.id, role=AppRole.admin)
        db.add(new_role)
        db.commit()
        
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": str(user.id)}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer", "id": user.id, "email": user.email}

@router.get("/me")
def read_users_me(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    roles = [r.role.value for r in current_user.roles]
    return {
        "id": current_user.id,
        "email": current_user.email,
        "full_name": current_user.full_name,
        "roles": roles
    }
