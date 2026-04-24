"""
Shared FastAPI dependencies.

Auth model: JWT access token in `Authorization: Bearer <token>` header.
A temporary `X-Admin-Token: <SECRET_KEY>` is still accepted for admin
endpoints so first-run ops (migrations, seed) can call the refresh trigger
before any admin user exists — it's disabled the moment an admin account
is present in the DB.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import JWTError, decode_token
from app.db.models import Subscription, User
from app.db.session import get_db

DbDep = Annotated[Session, Depends(get_db)]
_bearer = HTTPBearer(auto_error=False)


# ---------------------------------------------------------------------------
def _extract_user(
    db: Session,
    creds: HTTPAuthorizationCredentials | None,
    require_access: bool = True,
) -> User:
    if creds is None or creds.scheme.lower() != "bearer":
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "Missing or invalid Authorization header."
        )
    try:
        payload = decode_token(creds.credentials)
    except JWTError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"Invalid token: {exc}") from exc

    if require_access and payload.typ != "access":
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "Access token required (got refresh)."
        )

    user = db.get(User, int(payload.sub))
    if user is None or not user.is_active:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "User not found or inactive."
        )
    return user


def get_current_user(
    db: DbDep,
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> User:
    return _extract_user(db, creds, require_access=True)


def get_current_user_from_refresh(
    db: DbDep,
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> User:
    return _extract_user(db, creds, require_access=False)


CurrentUserDep = Annotated[User, Depends(get_current_user)]


# ---------------------------------------------------------------------------
def require_admin(user: CurrentUserDep) -> User:
    """JWT-backed admin check. Replaces the Phase A shared-secret header."""
    if not user.is_admin:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Admin privileges required."
        )
    return user


AdminUserDep = Annotated[User, Depends(require_admin)]


# ---------------------------------------------------------------------------
def require_bootstrap_or_admin(
    db: DbDep,
    x_admin_token: Annotated[str | None, Header(alias="X-Admin-Token")] = None,
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)] = None,
) -> None:
    """
    Bootstrap window: accept the shared-secret header IF no admin user exists
    in the DB yet. Once an admin account is registered, require JWT + is_admin.
    """
    any_admin = db.execute(
        select(User.id).where(User.is_admin.is_(True)).limit(1)
    ).first()

    if not any_admin:
        if x_admin_token and x_admin_token == settings.secret_key:
            return
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Bootstrap: provide X-Admin-Token header matching SECRET_KEY, or "
            "create an admin user first.",
        )

    # Regular admin path
    user = _extract_user(db, creds, require_access=True)
    if not user.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin privileges required.")


BootstrapOrAdminDep = Annotated[None, Depends(require_bootstrap_or_admin)]


# ---------------------------------------------------------------------------
def require_active_subscription(db: DbDep, user: CurrentUserDep) -> User:
    """
    Gate for analytical endpoints per PDF: "disable all analytical buttons
    until login and payment are completed."
    """
    now = datetime.now(timezone.utc)
    sub = db.execute(
        select(Subscription)
        .where(
            Subscription.user_id == user.id,
            Subscription.status == "completed",
            Subscription.expires_at > now,
        )
        .order_by(Subscription.expires_at.desc())
        .limit(1)
    ).scalar_one_or_none()

    if sub is None:
        raise HTTPException(
            status.HTTP_402_PAYMENT_REQUIRED,
            "Active subscription required to use analytical features.",
        )
    return user


SubscribedUserDep = Annotated[User, Depends(require_active_subscription)]


# ---------------------------------------------------------------------------
def require_disclaimer_accepted(user: CurrentUserDep) -> User:
    """Must have accepted the active disclaimer before analytical calls."""
    if user.disclaimer_accepted_at is None:
        raise HTTPException(
            status.HTTP_412_PRECONDITION_FAILED,
            "You must accept the disclaimer before using analytical tools.",
        )
    return user


DisclaimedUserDep = Annotated[User, Depends(require_disclaimer_accepted)]


# ---------------------------------------------------------------------------
# Request metadata helpers for audit logging
# ---------------------------------------------------------------------------
def client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None
