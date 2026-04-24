"""
PayTabs adapter.

PayTabs uses a server-key bearer token on requests and returns a
`redirect_url` for the hosted payment page. Webhooks are signed with an
HMAC header `signature`. Exact field names per PayTabs SA documentation.

As with the STC Pay adapter, real HTTP calls are gated behind a
`PAYTABS_TEST_MODE` flag so local development works without sandbox
credentials.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
from decimal import Decimal
from typing import Any

import httpx

from app.services.payments.base import (
    CheckoutRequest,
    CheckoutResponse,
    PaymentGateway,
    WebhookResult,
)

PAYTABS_BASE_URL = os.getenv("PAYTABS_BASE_URL", "https://secure.paytabs.sa")
PAYTABS_PROFILE_ID = os.getenv("PAYTABS_PROFILE_ID", "")
PAYTABS_SERVER_KEY = os.getenv("PAYTABS_SERVER_KEY", "")
PAYTABS_WEBHOOK_SECRET = os.getenv("PAYTABS_WEBHOOK_SECRET", "")
PAYTABS_TEST_MODE = os.getenv("PAYTABS_TEST_MODE", "true").lower() == "true"


class PayTabsGateway(PaymentGateway):
    name = "paytabs"

    def create_checkout(self, req: CheckoutRequest) -> CheckoutResponse:
        if PAYTABS_TEST_MODE:
            return CheckoutResponse(
                gateway_reference=f"test-paytabs-{req.merchant_reference}",
                redirect_url=f"{req.return_url}?cart_id={req.merchant_reference}&status=completed",
                raw={"test_mode": True},
            )

        payload = {
            "profile_id": PAYTABS_PROFILE_ID,
            "tran_type": "sale",
            "tran_class": "ecom",
            "cart_id": req.merchant_reference,
            "cart_description": req.description,
            "cart_currency": req.currency,
            "cart_amount": float(req.amount),
            "callback": (req.metadata or {}).get("callback_url"),
            "return": req.return_url,
            "customer_details": (req.metadata or {}).get("customer_details", {}),
        }
        r = httpx.post(
            f"{PAYTABS_BASE_URL}/payment/request",
            json=payload,
            headers={"Authorization": PAYTABS_SERVER_KEY},
            timeout=30,
        )
        r.raise_for_status()
        body = r.json()
        return CheckoutResponse(
            gateway_reference=body["tran_ref"],
            redirect_url=body["redirect_url"],
            raw=body,
        )

    def verify_webhook(self, headers: dict[str, str], body: bytes) -> WebhookResult:
        if PAYTABS_TEST_MODE:
            data = json.loads(body)
            return WebhookResult(
                merchant_reference=data["cart_id"],
                gateway_reference=data.get("tran_ref", f"test-{data['cart_id']}"),
                status="completed",
                amount=Decimal(str(data.get("cart_amount", 0))),
                currency=data.get("cart_currency", "SAR"),
                raw=data,
            )

        signature = headers.get("signature", "")
        expected = hmac.new(
            PAYTABS_WEBHOOK_SECRET.encode("utf-8"),
            body,
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(signature, expected):
            raise ValueError("Invalid PayTabs webhook signature")

        data = json.loads(body)
        return WebhookResult(
            merchant_reference=data["cart_id"],
            gateway_reference=data["tran_ref"],
            status=self._map_status(data.get("payment_result", {}).get("response_status", "")),
            amount=Decimal(str(data["cart_amount"])),
            currency=data["cart_currency"],
            raw=data,
        )

    def refund(self, gateway_reference: str, amount: Decimal | None = None) -> dict[str, Any]:
        if PAYTABS_TEST_MODE:
            return {"test_mode": True, "refunded": str(amount or "full")}

        payload: dict[str, Any] = {
            "profile_id": PAYTABS_PROFILE_ID,
            "tran_type": "refund",
            "tran_class": "ecom",
            "cart_currency": "SAR",
            "original_tran_ref": gateway_reference,
        }
        if amount is not None:
            payload["cart_amount"] = float(amount)
        r = httpx.post(
            f"{PAYTABS_BASE_URL}/payment/request",
            json=payload,
            headers={"Authorization": PAYTABS_SERVER_KEY},
            timeout=30,
        )
        r.raise_for_status()
        return r.json()

    # -----------------------------------------------------------------
    @staticmethod
    def _map_status(raw: str) -> str:
        return {
            "A": "completed",   # Authorised
            "H": "pending",     # Held
            "P": "pending",     # Pending
            "V": "refunded",    # Voided
            "D": "failed",      # Declined
            "E": "failed",      # Error
        }.get(raw.upper(), "pending")
