"""
Payment endpoints — subscription checkout + gateway webhooks.

Flow (per PDF §payment):
    1. Authenticated user hits POST /payments/subscribe → we create a pending
       Subscription row and a checkout at the active gateway.
    2. User is redirected to the gateway, pays, comes back to `return_url`.
    3. Gateway calls POST /payments/webhook/{gateway} asynchronously.
    4. We verify the signature, flip the Subscription row to "completed",
       set starts_at/expires_at, and emit an audit_log entry.
    5. `GET /auth/me` now shows `has_active_subscription=true` and the
       analytical endpoints become accessible.
"""
from __future__ import annotations

import json
import secrets
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import select

from app.api.deps import CurrentUserDep, DbDep, client_ip
from app.core.config import settings
from app.db.models import AdminConfig, AuditLog, Subscription
from app.schemas.payments import CheckoutIn, CheckoutOut, SubscriptionOut
from app.services.payments import CheckoutRequest, get_gateway

router = APIRouter(prefix="/payments", tags=["payments"])


# ---------------------------------------------------------------------------
def _config_float(db, key: str, fallback: float) -> float:
    row = db.get(AdminConfig, key)
    if row is None:
        return fallback
    try:
        return float(json.loads(row.value))
    except (ValueError, TypeError):
        return fallback


def _config_int(db, key: str, fallback: int) -> int:
    row = db.get(AdminConfig, key)
    if row is None:
        return fallback
    try:
        return int(json.loads(row.value))
    except (ValueError, TypeError):
        return fallback


# ---------------------------------------------------------------------------
@router.post("/subscribe", response_model=CheckoutOut, status_code=status.HTTP_201_CREATED)
def subscribe(
    payload: CheckoutIn,
    db: DbDep,
    user: CurrentUserDep,
    request: Request,
) -> CheckoutOut:
    gateway = get_gateway(db)
    amount = Decimal(str(_config_float(db, "subscription_price_sar", settings.subscription_price_sar)))
    merchant_reference = secrets.token_urlsafe(12)

    # Pre-create the Subscription row as pending — we flip it to completed
    # once the webhook arrives. This gives us an audit trail even if the
    # user abandons the payment flow.
    sub = Subscription(
        user_id=user.id,
        gateway=gateway.name,
        gateway_transaction_id=None,
        amount=amount,
        currency="SAR",
        status="pending",
    )
    db.add(sub)
    db.flush()

    try:
        checkout = gateway.create_checkout(CheckoutRequest(
            user_id=user.id,
            amount=amount,
            currency="SAR",
            merchant_reference=f"sub-{sub.id}-{merchant_reference}",
            return_url=payload.return_url,
            description="Tadawul Portfolio Optimizer — 30-day subscription",
            metadata={"user_email": user.email},
        ))
    except Exception as exc:
        db.rollback()
        raise HTTPException(502, f"Gateway error: {exc}") from exc

    sub.gateway_transaction_id = checkout.gateway_reference
    sub.raw_gateway_payload = checkout.raw
    db.add(AuditLog(
        user_id=user.id,
        action="payments.checkout_created",
        resource_type="subscriptions",
        resource_id=str(sub.id),
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
        request_method=request.method,
        request_path=str(request.url.path),
        details={"gateway": gateway.name, "amount": str(amount)},
    ))
    db.commit()

    return CheckoutOut(
        gateway=gateway.name,
        gateway_reference=checkout.gateway_reference,
        redirect_url=checkout.redirect_url,
        merchant_reference=f"sub-{sub.id}-{merchant_reference}",
        amount=amount,
        currency="SAR",
    )


# ---------------------------------------------------------------------------
@router.post("/webhook/{gateway_name}", status_code=status.HTTP_200_OK)
async def payment_webhook(
    gateway_name: str,
    db: DbDep,
    request: Request,
) -> dict:
    if gateway_name not in ("stcpay", "paytabs"):
        raise HTTPException(404, f"Unknown gateway: {gateway_name}")

    gateway = get_gateway(db, override=gateway_name)
    body = await request.body()
    headers = {k.lower(): v for k, v in request.headers.items()}

    try:
        result = gateway.verify_webhook(headers, body)
    except ValueError as exc:
        # Log and reject with 400 so the gateway retries correctly
        db.add(AuditLog(
            action="payments.webhook_invalid_signature",
            resource_type="subscriptions",
            ip_address=client_ip(request),
            request_method=request.method,
            request_path=str(request.url.path),
            details={"gateway": gateway_name, "error": str(exc)},
        ))
        db.commit()
        raise HTTPException(400, f"Invalid webhook: {exc}") from exc

    # Locate the matching Subscription row (we embedded `sub-{id}` in merchant_reference)
    ref = result.merchant_reference
    sub_id: int | None = None
    if ref.startswith("sub-"):
        try:
            sub_id = int(ref.split("-", 2)[1])
        except (IndexError, ValueError):
            sub_id = None

    sub = db.get(Subscription, sub_id) if sub_id else None
    if sub is None:
        sub = db.execute(
            select(Subscription).where(
                Subscription.gateway_transaction_id == result.gateway_reference
            )
        ).scalar_one_or_none()

    if sub is None:
        raise HTTPException(404, f"No subscription for merchant_reference={ref}")

    # Idempotency: webhooks can be delivered more than once
    if sub.status == "completed" and result.status == "completed":
        return {"ok": True, "already_completed": True}

    sub.status = result.status
    sub.gateway_transaction_id = result.gateway_reference
    sub.raw_gateway_payload = result.raw

    if result.status == "completed":
        duration = _config_int(db, "subscription_duration_days", settings.subscription_duration_days)
        now = datetime.now(timezone.utc)
        sub.starts_at = now
        sub.expires_at = now + timedelta(days=duration)

    db.add(AuditLog(
        user_id=sub.user_id,
        action=f"payments.webhook_{result.status}",
        resource_type="subscriptions",
        resource_id=str(sub.id),
        ip_address=client_ip(request),
        request_method=request.method,
        request_path=str(request.url.path),
        details={
            "gateway": gateway_name,
            "amount": str(result.amount),
            "currency": result.currency,
            "gateway_reference": result.gateway_reference,
        },
    ))
    db.commit()
    return {"ok": True, "status": result.status}


# ---------------------------------------------------------------------------
@router.get("/subscriptions", response_model=list[SubscriptionOut])
def list_my_subscriptions(
    db: DbDep, user: CurrentUserDep
) -> list[SubscriptionOut]:
    rows = db.execute(
        select(Subscription)
        .where(Subscription.user_id == user.id)
        .order_by(Subscription.created_at.desc())
    ).scalars().all()
    return [SubscriptionOut.model_validate(r) for r in rows]
