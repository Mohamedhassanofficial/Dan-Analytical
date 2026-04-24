"""Pydantic schemas for the payments API."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field


class CheckoutIn(BaseModel):
    return_url: str = Field(..., description="Where the user is returned after payment.")


class CheckoutOut(BaseModel):
    gateway: str
    gateway_reference: str
    redirect_url: str
    merchant_reference: str
    amount: Decimal
    currency: str


class SubscriptionOut(BaseModel):
    id: int
    gateway: str
    gateway_transaction_id: str | None
    amount: Decimal
    currency: str
    status: Literal["pending", "completed", "failed", "refunded"]
    starts_at: datetime | None
    expires_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}
