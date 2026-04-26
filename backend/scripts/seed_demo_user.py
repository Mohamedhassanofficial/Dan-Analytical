"""
Idempotent demo-user seed for the Render testing deployment.

Creates (or refreshes) demo@tadawul.local with:
  - is_admin=True so the admin pages work for Loay's first walkthrough
  - disclaimer accepted on the latest disclaimer version
  - active subscription that expires 365 days from now

Re-runs are safe: existing user is upgraded in-place; password hash is
refreshed only if it doesn't yet validate.

Usage (from backend/):
    python -m scripts.seed_demo_user
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app.core.security import hash_password, verify_password  # noqa: E402
from app.db.models import (  # noqa: E402
    DisclaimerVersion,
    Subscription,
    User,
    UserDisclaimerAcceptance,
)
from app.db.session import SessionLocal  # noqa: E402


DEMO_EMAIL = os.environ.get("DEMO_USER_EMAIL", "demo@tadawul.local")
DEMO_PASSWORD = os.environ.get("DEMO_USER_PASSWORD", "demo-video-2026")
DEMO_NATIONAL_ID = os.environ.get("DEMO_USER_NATIONAL_ID", "1000000001")
DEMO_MOBILE = os.environ.get("DEMO_USER_MOBILE", "+966500000001")


def seed() -> dict:
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        user = db.execute(select(User).where(User.email == DEMO_EMAIL)).scalar_one_or_none()
        created = False

        if user is None:
            user = User(
                email=DEMO_EMAIL,
                national_id=DEMO_NATIONAL_ID,
                mobile=DEMO_MOBILE,
                password_hash=hash_password(DEMO_PASSWORD),
                full_name_ar="حساب تجريبي",
                full_name_en="Demo Account",
                preferred_locale="ar",
                is_active=True,
                is_admin=True,
            )
            db.add(user)
            db.flush()
            created = True
        else:
            # Refresh privileges + ensure password matches the documented one.
            user.is_admin = True
            user.is_active = True
            if not verify_password(DEMO_PASSWORD, user.password_hash):
                user.password_hash = hash_password(DEMO_PASSWORD)

        # Disclaimer acceptance — pick the most recent active version
        latest_disclaimer = db.execute(
            select(DisclaimerVersion).order_by(DisclaimerVersion.id.desc()).limit(1)
        ).scalar_one_or_none()
        if latest_disclaimer is not None:
            existing_acceptance = db.execute(
                select(UserDisclaimerAcceptance).where(
                    UserDisclaimerAcceptance.user_id == user.id,
                    UserDisclaimerAcceptance.disclaimer_id == latest_disclaimer.id,
                )
            ).scalar_one_or_none()
            if existing_acceptance is None:
                db.add(
                    UserDisclaimerAcceptance(
                        user_id=user.id,
                        disclaimer_id=latest_disclaimer.id,
                        accepted_at=now,
                    )
                )
            user.disclaimer_accepted_at = now

        # Active subscription (1-year) — only insert if there's no current
        # active one. This keeps re-runs idempotent.
        active_sub = db.execute(
            select(Subscription)
            .where(Subscription.user_id == user.id)
            .where(Subscription.status == "completed")
            .order_by(Subscription.expires_at.desc())
            .limit(1)
        ).scalar_one_or_none()
        if active_sub is None or (active_sub.expires_at and active_sub.expires_at < now):
            db.add(
                Subscription(
                    user_id=user.id,
                    gateway="stcpay",
                    gateway_transaction_id=f"demo-seed-{int(now.timestamp())}",
                    amount=Decimal("0.00"),
                    currency="SAR",
                    status="completed",
                    starts_at=now,
                    expires_at=now + timedelta(days=365),
                )
            )

        db.commit()
        return {
            "email": user.email,
            "id": user.id,
            "is_admin": user.is_admin,
            "created": created,
        }


if __name__ == "__main__":
    info = seed()
    print(
        "✓ demo user "
        + ("created" if info["created"] else "refreshed")
        + f" — {info['email']} (id={info['id']}, is_admin={info['is_admin']})"
    )
