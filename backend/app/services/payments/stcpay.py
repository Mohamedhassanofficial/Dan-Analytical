"""
STC Pay adapter.

STC Pay uses OAuth2 client credentials for API auth and HMAC-SHA256
signatures on webhook bodies. Exact endpoint URLs and field names are
specified in STC Pay Merchant Portal documentation — until we have the
real sandbox credentials, this adapter uses placeholders marked with
`TODO(stcpay)` and a `test_mode` that simulates a successful payment
without making real HTTP calls (activated when STCPAY_TEST_MODE=true).

When the client provides real credentials, replace the TODOs and remove
the test-mode branch.
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

STCPAY_BASE_URL = os.getenv("STCPAY_BASE_URL", "https://api.stcpay.com.sa/v2")  # TODO(stcpay)
STCPAY_MERCHANT_ID = os.getenv("STCPAY_MERCHANT_ID", "")
STCPAY_CLIENT_ID = os.getenv("STCPAY_CLIENT_ID", "")
STCPAY_CLIENT_SECRET = os.getenv("STCPAY_CLIENT_SECRET", "")
STCPAY_WEBHOOK_SECRET = os.getenv("STCPAY_WEBHOOK_SECRET", "")
STCPAY_TEST_MODE = os.getenv("STCPAY_TEST_MODE", "true").lower() == "true"


class STCPayGateway(PaymentGateway):
    name = "stcpay"

    def create_checkout(self, req: CheckoutRequest) -> CheckoutResponse:
        if STCPAY_TEST_MODE:
            return CheckoutResponse(
                gateway_reference=f"test-stcpay-{req.merchant_reference}",
                redirect_url=f"{req.return_url}?mr={req.merchant_reference}&status=completed",
                raw={"test_mode": True, "merchant_reference": req.merchant_reference},
            )

        token = self._oauth_token()
        payload = {
            "merchantId": STCPAY_MERCHANT_ID,
            "amount": str(req.amount),
            "currency": req.currency,
            "merchantReference": req.merchant_reference,
            "returnUrl": req.return_url,
            "description": req.description,
        }
        r = httpx.post(
            f"{STCPAY_BASE_URL}/payments",  # TODO(stcpay): confirm path
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
            timeout=30,
        )
        r.raise_for_status()
        body = r.json()
        return CheckoutResponse(
            gateway_reference=body["paymentId"],    # TODO(stcpay): confirm key
            redirect_url=body["redirectUrl"],        # TODO(stcpay): confirm key
            raw=body,
        )

    def verify_webhook(self, headers: dict[str, str], body: bytes) -> WebhookResult:
        if STCPAY_TEST_MODE:
            data = json.loads(body)
            return WebhookResult(
                merchant_reference=data["merchantReference"],
                gateway_reference=data.get("paymentId", f"test-{data['merchantReference']}"),
                status="completed",
                amount=Decimal(str(data["amount"])),
                currency=data.get("currency", "SAR"),
                raw=data,
            )

        signature = headers.get("x-stcpay-signature", "")
        expected = hmac.new(
            STCPAY_WEBHOOK_SECRET.encode("utf-8"),
            body,
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(signature, expected):
            raise ValueError("Invalid STC Pay webhook signature")

        data = json.loads(body)
        return WebhookResult(
            merchant_reference=data["merchantReference"],
            gateway_reference=data["paymentId"],
            status=self._map_status(data["status"]),
            amount=Decimal(str(data["amount"])),
            currency=data["currency"],
            raw=data,
        )

    def refund(self, gateway_reference: str, amount: Decimal | None = None) -> dict[str, Any]:
        if STCPAY_TEST_MODE:
            return {"test_mode": True, "refunded": str(amount or "full")}

        token = self._oauth_token()
        payload: dict[str, Any] = {"paymentId": gateway_reference}
        if amount is not None:
            payload["amount"] = str(amount)
        r = httpx.post(
            f"{STCPAY_BASE_URL}/refunds",  # TODO(stcpay)
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
            timeout=30,
        )
        r.raise_for_status()
        return r.json()

    # -----------------------------------------------------------------
    def _oauth_token(self) -> str:
        """Client credentials grant. STC Pay returns `access_token`."""
        r = httpx.post(
            f"{STCPAY_BASE_URL}/oauth/token",  # TODO(stcpay)
            data={
                "grant_type": "client_credentials",
                "client_id": STCPAY_CLIENT_ID,
                "client_secret": STCPAY_CLIENT_SECRET,
            },
            timeout=30,
        )
        r.raise_for_status()
        return r.json()["access_token"]

    @staticmethod
    def _map_status(raw: str) -> str:
        return {
            "SUCCESS": "completed",
            "COMPLETED": "completed",
            "FAILED": "failed",
            "DECLINED": "failed",
            "REFUNDED": "refunded",
            "PENDING": "pending",
        }.get(raw.upper(), "pending")
