"""
Auth endpoints — register, login, refresh, me, accept-disclaimer.

Matches the PDF brief's requirements:
    - Registration via national ID + mobile + email + password
    - Mandatory disclaimer acceptance before analytical tools unlock
    - Login returns access + refresh JWTs
    - All significant events are audit-logged
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request, Response, status
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError

from app.api.deps import (
    CurrentUserDep,
    DbDep,
    client_ip,
    get_current_user_from_refresh,
)
from app.core.config import settings
from app.core.security import (
    REFRESH_TOKEN_TTL_DAYS,
    create_access_token,
    create_refresh_token,
    hash_password,
    verify_password,
)
from app.db.models import (
    AuditLog,
    DisclaimerVersion,
    Subscription,
    User,
    UserDisclaimerAcceptance,
)
from app.schemas.auth import (
    DisclaimerAcceptance,
    DisclaimerOut,
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    TokenPair,
    UserOut,
)
from fastapi import Depends

router = APIRouter(prefix="/auth", tags=["auth"])


# ---------------------------------------------------------------------------
def _token_pair(user: User) -> TokenPair:
    return TokenPair(
        access_token=create_access_token(user.id, is_admin=user.is_admin),
        refresh_token=create_refresh_token(user.id, is_admin=user.is_admin),
        access_expires_in_sec=settings.access_token_ttl_min * 60,
        refresh_expires_in_sec=REFRESH_TOKEN_TTL_DAYS * 86_400,
    )


def _has_active_subscription(db, user_id: int) -> bool:
    now = datetime.now(timezone.utc)
    return db.execute(
        select(Subscription.id)
        .where(
            Subscription.user_id == user_id,
            Subscription.status == "completed",
            Subscription.expires_at > now,
        )
        .limit(1)
    ).first() is not None


def _user_out(db, user: User) -> UserOut:
    return UserOut(
        id=user.id,
        national_id=user.national_id,
        mobile=user.mobile,
        email=user.email,
        full_name_ar=user.full_name_ar,
        full_name_en=user.full_name_en,
        preferred_locale=user.preferred_locale,
        is_active=user.is_active,
        is_admin=user.is_admin,
        disclaimer_accepted_at=user.disclaimer_accepted_at,
        last_login_at=user.last_login_at,
        has_active_subscription=_has_active_subscription(db, user.id),
    )


# ---------------------------------------------------------------------------
@router.post("/register", status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, db: DbDep, request: Request) -> UserOut:
    # Conflict check before insert so error messages stay specific.
    clash = db.execute(
        select(User).where(
            or_(
                User.national_id == payload.national_id,
                User.mobile == payload.mobile,
                User.email == payload.email.lower(),
            )
        )
    ).scalar_one_or_none()
    if clash is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "An account already exists with the provided national_id, mobile, or email.",
        )

    user = User(
        national_id=payload.national_id,
        mobile=payload.mobile,
        email=payload.email.lower(),
        password_hash=hash_password(payload.password),
        full_name_ar=payload.full_name_ar,
        full_name_en=payload.full_name_en,
        preferred_locale=payload.preferred_locale,
    )
    db.add(user)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Registration conflict on unique field."
        ) from None

    db.add(
        AuditLog(
            user_id=user.id,
            action="auth.register",
            resource_type="users",
            resource_id=str(user.id),
            ip_address=client_ip(request),
            user_agent=request.headers.get("user-agent"),
            request_method=request.method,
            request_path=str(request.url.path),
            details={"locale": user.preferred_locale},
        )
    )
    db.commit()
    db.refresh(user)
    return _user_out(db, user)


# ---------------------------------------------------------------------------
@router.post("/login", response_model=TokenPair)
def login(payload: LoginRequest, db: DbDep, request: Request) -> TokenPair:
    ident = payload.identifier.strip().lower()
    user = db.execute(
        select(User).where(
            or_(
                User.email == ident,
                User.mobile == payload.identifier.strip(),
                User.national_id == payload.identifier.strip(),
            )
        )
    ).scalar_one_or_none()

    ok = user is not None and user.is_active and verify_password(
        payload.password, user.password_hash
    )
    if not ok:
        # Log the failed attempt (no user_id if identifier didn't match)
        db.add(
            AuditLog(
                user_id=user.id if user else None,
                action="auth.login_failed",
                ip_address=client_ip(request),
                user_agent=request.headers.get("user-agent"),
                request_method=request.method,
                request_path=str(request.url.path),
                details={"identifier": payload.identifier[:64]},
            )
        )
        db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials.")

    user.last_login_at = datetime.now(timezone.utc)
    user.last_login_ip = client_ip(request)
    db.add(
        AuditLog(
            user_id=user.id,
            action="auth.login",
            ip_address=client_ip(request),
            user_agent=request.headers.get("user-agent"),
            request_method=request.method,
            request_path=str(request.url.path),
        )
    )
    db.commit()
    db.refresh(user)
    return _token_pair(user)


# ---------------------------------------------------------------------------
@router.post("/refresh", response_model=TokenPair)
def refresh_tokens(
    payload: RefreshRequest,
    db: DbDep,
    user: User = Depends(get_current_user_from_refresh),
) -> TokenPair:
    """
    Exchange a refresh token for a fresh access+refresh pair. The caller
    sends the refresh token in the `Authorization: Bearer` header (matches
    get_current_user_from_refresh dependency); `payload.refresh_token` is
    included for future revocation-list support.
    """
    # `payload` is currently advisory — dependency already validated the header.
    _ = payload.refresh_token
    return _token_pair(user)


# ---------------------------------------------------------------------------
@router.get("/me", response_model=UserOut)
def me(db: DbDep, user: CurrentUserDep) -> UserOut:
    return _user_out(db, user)


# ---------------------------------------------------------------------------
@router.get("/disclaimer/active", response_model=DisclaimerOut)
def active_disclaimer(db: DbDep) -> DisclaimerOut:
    """Return the currently active disclaimer (bilingual). Public endpoint."""
    v = db.execute(
        select(DisclaimerVersion)
        .where(DisclaimerVersion.is_active.is_(True))
        .order_by(DisclaimerVersion.id.desc())
        .limit(1)
    ).scalar_one_or_none()
    if v is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "No active disclaimer configured."
        )
    return DisclaimerOut.model_validate(v)


@router.post("/disclaimer/accept")
def accept_disclaimer(
    payload: DisclaimerAcceptance,
    db: DbDep,
    request: Request,
    user: CurrentUserDep,
) -> dict:
    v = db.execute(
        select(DisclaimerVersion).where(DisclaimerVersion.version == payload.disclaimer_version)
    ).scalar_one_or_none()
    if v is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, f"Unknown disclaimer version: {payload.disclaimer_version}"
        )

    ip = client_ip(request)
    now = datetime.now(timezone.utc)

    acceptance = UserDisclaimerAcceptance(
        user_id=user.id,
        disclaimer_id=v.id,
        accepted_at=now,
        ip_address=ip,
    )
    db.add(acceptance)
    user.disclaimer_accepted_at = now
    db.add(
        AuditLog(
            user_id=user.id,
            action="auth.disclaimer_accepted",
            resource_type="disclaimer_versions",
            resource_id=payload.disclaimer_version,
            ip_address=ip,
            user_agent=request.headers.get("user-agent"),
            request_method=request.method,
            request_path=str(request.url.path),
        )
    )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        # Already accepted — idempotent, do nothing.
    return {"ok": True, "version": payload.disclaimer_version}
