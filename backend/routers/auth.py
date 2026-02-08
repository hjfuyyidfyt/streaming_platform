"""
User Authentication Router.
Handles user registration, login, and token refresh.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlmodel import Session, select
from pydantic import BaseModel, EmailStr
import jwt  # PyJWT
from datetime import datetime, timedelta
from typing import Optional
import os
from dotenv import load_dotenv

from ..database import get_session
from ..models import User, Playlist

load_dotenv()

router = APIRouter(
    prefix="/auth",
    tags=["authentication"]
)

# Security config
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "your-super-secret-key-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 7 days

import bcrypt
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login", auto_error=False)


# Pydantic schemas
class UserRegister(BaseModel):
    username: str
    email: EmailStr
    password: str
    display_name: Optional[str] = None


class UserLogin(BaseModel):
    email: str
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str


class UserPublic(BaseModel):
    id: int
    username: str
    email: str
    display_name: Optional[str]
    avatar_url: Optional[str]
    created_at: datetime


# Helper functions
def verify_password(plain_password: str, hashed_password: str) -> bool:
    # Bcrypt has 72 byte limit - truncate password
    password_bytes = plain_password.encode('utf-8')[:72]
    return bcrypt.checkpw(password_bytes, hashed_password.encode('utf-8'))


def get_password_hash(password: str) -> str:
    # Bcrypt has 72 byte limit - truncate password
    password_bytes = password.encode('utf-8')[:72]
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password_bytes, salt).decode('utf-8')


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    session: Session = Depends(get_session)
) -> Optional[User]:
    """Get current user from JWT token. Returns None if not authenticated."""
    if not token:
        return None
    
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id_str = payload.get("sub")
        if user_id_str is None:
            return None
        user_id = int(user_id_str)  # Convert string back to int
    except (jwt.PyJWTError, ValueError):
        return None
    
    user = session.get(User, user_id)
    return user


async def require_user(
    current_user: Optional[User] = Depends(get_current_user)
) -> User:
    """Require authenticated user. Raises 401 if not logged in."""
    if not current_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return current_user


# Endpoints
@router.post("/register", response_model=UserPublic)
async def register(
    user_data: UserRegister,
    session: Session = Depends(get_session)
):
    """Register a new user account."""
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        # Check if username exists
        existing = session.exec(
            select(User).where(User.username == user_data.username)
        ).first()
        if existing:
            raise HTTPException(status_code=400, detail="Username already taken")
        
        # Check if email exists
        existing = session.exec(
            select(User).where(User.email == user_data.email)
        ).first()
        if existing:
            raise HTTPException(status_code=400, detail="Email already registered")
        
        # Create user
        user = User(
            username=user_data.username,
            email=user_data.email,
            password_hash=get_password_hash(user_data.password),
            display_name=user_data.display_name or user_data.username
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        
        # Create default "Watch Later" playlist
        watch_later = Playlist(
            user_id=user.id,
            name="Watch Later",
            is_watch_later=True,
            is_public=False
        )
        session.add(watch_later)
        session.commit()
        
        logger.info(f"User registered successfully: {user.username}")
        return user
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Registration error: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Registration failed: {str(e)}")


@router.post("/login", response_model=Token)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    session: Session = Depends(get_session)
):
    """Login with email/username and password."""
    # Find user by email or username
    user = session.exec(
        select(User).where(
            (User.email == form_data.username) | (User.username == form_data.username)
        )
    ).first()
    
    if not user or not verify_password(form_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email/username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if not user.is_active:
        raise HTTPException(status_code=400, detail="Account is deactivated")
    
    # Create token - sub must be string for PyJWT
    access_token = create_access_token(data={"sub": str(user.id)})
    
    return {"access_token": access_token, "token_type": "bearer"}


@router.get("/me", response_model=UserPublic)
async def get_me(current_user: User = Depends(require_user)):
    """Get current logged-in user info."""
    return current_user


@router.post("/logout")
async def logout():
    """Logout (client should discard token)."""
    return {"message": "Logged out successfully"}
