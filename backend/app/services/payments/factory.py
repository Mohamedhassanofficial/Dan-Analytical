"""Factory that returns the currently-active PaymentGateway."""
from __future__ import annotations

import json

from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import AdminConfig
from app.services.payments.base import PaymentGateway
from app.services.payments.paytabs import PayTabsGateway
from app.services.payments.stcpay import STCPayGateway


def _resolve_name(db: Session) -> str:
    row = db.get(AdminConfig, "payment_gateway")
    if row is not None:
        try:
            return str(json.loads(row.value)).lower()
        except (ValueError, TypeError):
            pass
    return settings.payment_gateway


def get_gateway(db: Session, override: str | None = None) -> PaymentGateway:
    name = (override or _resolve_name(db)).lower()
    if name == "stcpay":
        return STCPayGateway()
    if name == "paytabs":
        return PayTabsGateway()
    raise ValueError(f"Unknown or disabled payment gateway: {name!r}")
