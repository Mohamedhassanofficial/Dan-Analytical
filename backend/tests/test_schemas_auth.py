"""Validation of auth payload schemas — the first line of PDPL-aware input validation."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.auth import RegisterRequest


VALID_PAYLOAD = {
    "national_id": "1234567890",
    "mobile": "+966501234567",
    "email": "investor@example.com",
    "password": "correct-horse-battery",
    "full_name_ar": "مستثمر تجريبي",
    "full_name_en": "Test Investor",
    "preferred_locale": "ar",
}


def test_register_accepts_valid_payload():
    req = RegisterRequest(**VALID_PAYLOAD)
    assert req.mobile == "+966501234567"


@pytest.mark.parametrize("bad_id", ["123456789", "12345678901", "abcd123456", ""])
def test_register_rejects_bad_national_id(bad_id):
    bad = {**VALID_PAYLOAD, "national_id": bad_id}
    with pytest.raises(ValidationError):
        RegisterRequest(**bad)


@pytest.mark.parametrize("bad_mobile", ["0501234567890", "+1234567890", "0412345678", "not-a-mobile"])
def test_register_rejects_bad_mobile(bad_mobile):
    bad = {**VALID_PAYLOAD, "mobile": bad_mobile}
    with pytest.raises(ValidationError):
        RegisterRequest(**bad)


def test_register_rejects_short_password():
    bad = {**VALID_PAYLOAD, "password": "short"}
    with pytest.raises(ValidationError):
        RegisterRequest(**bad)


def test_register_accepts_05_mobile_prefix():
    req = RegisterRequest(**{**VALID_PAYLOAD, "mobile": "0501234567"})
    assert req.mobile == "0501234567"
