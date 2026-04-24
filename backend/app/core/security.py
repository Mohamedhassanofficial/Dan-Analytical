"""
Security primitives: password hashing + JWT access/refresh tokens.

Design choices (ratified with the PDF's SDAIA/PDPL requirements):
  - bcrypt with `settings.bcrypt_rounds` (default 12) — balances cost vs UX
  - JWTs use HS256 with the long-lived `settings.secret_key`
  - Access tokens: short-lived (default 30 min)
  - Refresh tokens: 14 days, rotation-safe, revocable (revocation list is a
    Phase B+ enhancement — a minimal version uses a `jti` claim and the
    audit_log; full list in Redis is on the roadmap)

Public surface:
    hash_password, verify_password
    create_access_token, create_refresh_token
    decode_token -> TokenPayload | raises JWTError

Callers should import through `app.api.deps` (not this module directly) so the
dependency graph stays tidy.
"""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from typing import Literal

from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel

from app.core.config import settings

_pwd_ctx = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
    bcrypt__rounds=settings.bcrypt_rounds,
)

ALGORITHM = "HS256"
REFRESH_TOKEN_TTL_DAYS = 14


class TokenPayload(BaseModel):
    sub: str                         # user_id as string
    exp: int                         # unix timestamp
    iat: int
    jti: str                         # unique token id (for revocation)
    typ: Literal["access", "refresh"]
    is_admin: bool = False


# ---------------------------------------------------------------------------
# Passwords
# ---------------------------------------------------------------------------
def hash_password(plain: str) -> str:
    return _pwd_ctx.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return _pwd_ctx.verify(plain, hashed)
    except ValueError:
        return False


# ---------------------------------------------------------------------------
# JWT
# ---------------------------------------------------------------------------
def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _build_token(
    user_id: int, typ: Literal["access", "refresh"], is_admin: bool, ttl: timedelta
) -> str:
    now = _now_utc()
    payload = {
        "sub": str(user_id),
        "exp": int((now + ttl).timestamp()),
        "iat": int(now.timestamp()),
        "jti": secrets.token_urlsafe(16),
        "typ": typ,
        "is_admin": is_admin,
    }
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def create_access_token(user_id: int, is_admin: bool = False) -> str:
    return _build_token(
        user_id, "access", is_admin,
        ttl=timedelta(minutes=settings.access_token_ttl_min),
    )


def create_refresh_token(user_id: int, is_admin: bool = False) -> str:
    return _build_token(
        user_id, "refresh", is_admin,
        ttl=timedelta(days=REFRESH_TOKEN_TTL_DAYS),
    )


def decode_token(token: str) -> TokenPayload:
    """Raise JWTError on invalid / expired tokens."""
    data = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
    return TokenPayload(**data)


__all__ = [
    "hash_password",
    "verify_password",
    "create_access_token",
    "create_refresh_token",
    "decode_token",
    "TokenPayload",
    "JWTError",
]
