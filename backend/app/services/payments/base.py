"""
Abstract PaymentGateway interface + shared data types.

Both STCPay and PayTabs adapters implement this interface so the API handlers
don't care which one is active — the factory (services/payments/factory.py)
returns the right adapter based on `admin_config.payment_gateway`.

All gateway-specific details (headers, signature schemes, redirect URLs)
are hidden behind these methods.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Literal

PaymentStatus = Literal["pending", "completed", "failed", "refunded"]


@dataclass
class CheckoutRequest:
    user_id: int
    amount: Decimal
    currency: str                   # ISO-4217, usually "SAR"
    merchant_reference: str         # our own unique id; also used for idempotency
    return_url: str                 # where to redirect the user after payment
    description: str = "Tadawul Portfolio Optimizer subscription"
    metadata: dict[str, Any] | None = None


@dataclass
class CheckoutResponse:
    gateway_reference: str          # transaction id returned by the gateway
    redirect_url: str               # user is sent here to complete payment
    raw: dict[str, Any]             # full gateway response (for audit)


@dataclass
class WebhookResult:
    merchant_reference: str
    gateway_reference: str
    status: PaymentStatus
    amount: Decimal
    currency: str
    raw: dict[str, Any]


class PaymentGateway(ABC):
    """
    All adapters must implement `create_checkout` and `verify_webhook`.
    They should be pure I/O — no DB writes; the caller does that.
    """

    name: str  # "stcpay" | "paytabs"

    @abstractmethod
    def create_checkout(self, req: CheckoutRequest) -> CheckoutResponse:
        """Create a payment and return the redirect URL the user must visit."""

    @abstractmethod
    def verify_webhook(self, headers: dict[str, str], body: bytes) -> WebhookResult:
        """
        Validate the webhook signature and parse the payload. Raise
        `ValueError` if the signature is invalid — the caller will respond 400.
        """

    @abstractmethod
    def refund(self, gateway_reference: str, amount: Decimal | None = None) -> dict[str, Any]:
        """Issue a refund. Optional amount means full refund."""
