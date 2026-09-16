import os
import secrets
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

# pyrefly: ignore [missing-import]
import bcrypt
# pyrefly: ignore [missing-import]
import jwt
from fastapi import Depends, HTTPException, Request
# pyrefly: ignore [missing-import]
from sqlalchemy.orm import Session

from database import get_db

BASE_DIR = Path(__file__).resolve().parent

# --- SECRET KEY MANAGEMENT ---
_env_secret = os.environ.get("SECRET_KEY")
if _env_secret:
    SECRET_KEY = _env_secret
else:
    # Use persistent fallback file for local dev so server reload doesn't invalidate sessions
    _secret_file = BASE_DIR / ".jwt_secret"
    if _secret_file.exists():
        SECRET_KEY = _secret_file.read_text(encoding="utf-8").strip()
    else:
        SECRET_KEY = secrets.token_hex(32)
        try:
            _secret_file.write_text(SECRET_KEY, encoding="utf-8")
        except Exception:
            pass
    print("[SECURITY WARNING] SECRET_KEY is not set in environment! Using local fallback key.")

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_DAYS = 7

# In production (or if COOKIE_SECURE is set), set Secure flag on cookie
IS_COOKIE_SECURE = (
    os.environ.get("ENVIRONMENT", "").lower() == "production"
    or os.environ.get("COOKIE_SECURE", "").lower() in ("true", "1")
)


# --- PASSWORD HASHING ---
def hash_password(password: str) -> str:
    """Hash password using bcrypt."""
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify password against bcrypt hash."""
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            hashed_password.encode("utf-8")
        )
    except Exception:
        return False


# --- JWT TOKEN MANAGEMENT ---
def create_access_token(user_id: int, username: str, expires_delta: Optional[timedelta] = None) -> str:
    """Create a signed JWT access token."""
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS)

    payload = {
        "sub": str(user_id),
        "username": username,
        "exp": expire
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> Optional[dict]:
    """Safely decode JWT access token, catching all validation and expiration errors."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError, Exception):
        return None


# --- LOGIN RATE LIMITER (In-Memory Sliding Window) ---
class LoginRateLimiter:
    """Rate limiter to protect against brute-force login attacks."""
    def __init__(self, max_attempts: int = 5, window_seconds: int = 60):
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self.attempts = {}  # key: (ip, username) -> list of timestamps

    def _clean_old(self, key: tuple, now: float):
        if key in self.attempts:
            self.attempts[key] = [t for t in self.attempts[key] if now - t < self.window_seconds]
            if not self.attempts[key]:
                del self.attempts[key]

    def is_rate_limited(self, ip: str, username: str) -> bool:
        now = time.time()
        key = (ip, username.lower().strip())
        self._clean_old(key, now)
        return len(self.attempts.get(key, [])) >= self.max_attempts

    def record_failure(self, ip: str, username: str):
        now = time.time()
        key = (ip, username.lower().strip())
        self._clean_old(key, now)
        if key not in self.attempts:
            self.attempts[key] = []
        self.attempts[key].append(now)

    def reset(self, ip: str, username: str):
        key = (ip, username.lower().strip())
        if key in self.attempts:
            del self.attempts[key]


login_rate_limiter = LoginRateLimiter(max_attempts=5, window_seconds=60)


# --- FASTAPI AUTH DEPENDENCIES ---
def extract_token_from_request(request: Request) -> Optional[str]:
    """Extract token from HttpOnly cookie or Authorization: Bearer header."""
    cookie_token = request.cookies.get("access_token")
    if cookie_token:
        return cookie_token

    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        return auth_header[7:].strip()

    return None


def get_current_user_optional(request: Request, db: Session = Depends(get_db)):
    """Optional user dependency for HTML pages. Never throws 500 on invalid/expired token."""
    from models import User

    token = extract_token_from_request(request)
    if not token:
        return None

    payload = decode_access_token(token)
    if not payload:
        return None

    user_id_str = payload.get("sub")
    if not user_id_str:
        return None

    try:
        user_id = int(user_id_str)
        user = db.query(User).filter(User.id == user_id).first()
        return user
    except Exception:
        return None


def get_current_user(request: Request, db: Session = Depends(get_db)):
    """Strict user dependency for protected API endpoints. Raises 401 if unauthenticated."""
    user = get_current_user_optional(request, db)
    if not user:
        raise HTTPException(
            status_code=401,
            detail="Chưa đăng nhập hoặc phiên làm việc đã hết hạn."
        )
    return user
