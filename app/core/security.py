import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from jose import jwt
from passlib.context import CryptContext

from app.core.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

ALGO = "HS256"


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(password, password_hash)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def new_jti() -> str:
    return secrets.token_hex(16)  # 32 chars


def make_access_token(user_id: str) -> str:
    exp = _now() + timedelta(minutes=settings.ACCESS_TTL_MIN)
    payload: dict[str, Any] = {
        "iss": settings.JWT_ISSUER,
        "sub": user_id,
        "type": "access",
        "exp": exp,
        "iat": _now(),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=ALGO)


def make_refresh_token(user_id: str, jti: str) -> str:
    exp = _now() + timedelta(days=settings.REFRESH_TTL_DAYS)
    payload: dict[str, Any] = {
        "iss": settings.JWT_ISSUER,
        "sub": user_id,
        "type": "refresh",
        "jti": jti,
        "exp": exp,
        "iat": _now(),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=ALGO)


def decode_token(token: str) -> dict[str, Any]:
    return jwt.decode(
        token, settings.JWT_SECRET, algorithms=[ALGO], issuer=settings.JWT_ISSUER
    )
