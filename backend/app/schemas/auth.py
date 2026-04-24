"""Pydantic schemas for auth endpoints."""
from __future__ import annotations

import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, field_validator

# Mobile: either Saudi (+9665XXXXXXXX / 05XXXXXXXX) or any international
# E.164-like format (+<country><8-14 digits>). Non-Saudi numbers are allowed
# for dev / regional testing; production PDPL posture may tighten this.
_MOBILE_RE = re.compile(r"^(?:\+\d{8,15}|05\d{8})$")
# Saudi national ID: exactly 10 digits
_NATIONAL_ID_RE = re.compile(r"^\d{10}$")


class RegisterRequest(BaseModel):
    national_id: str = Field(..., description="10-digit Saudi national ID / iqama.")
    mobile: str = Field(..., description="Saudi mobile (+9665XXXXXXXX or 05XXXXXXXX).")
    email: EmailStr
    password: str = Field(..., min_length=10, max_length=72)
    full_name_ar: str | None = Field(None, max_length=255)
    full_name_en: str | None = Field(None, max_length=255)
    preferred_locale: Literal["ar", "en"] = "ar"

    @field_validator("national_id")
    @classmethod
    def _check_national_id(cls, v: str) -> str:
        v = v.strip()
        if not _NATIONAL_ID_RE.match(v):
            raise ValueError("national_id must be exactly 10 digits")
        return v

    @field_validator("mobile")
    @classmethod
    def _check_mobile(cls, v: str) -> str:
        v = v.strip().replace(" ", "")
        if not _MOBILE_RE.match(v):
            raise ValueError("mobile must be an international format (+<country><digits>) or a Saudi local 05XXXXXXXX")
        return v


class LoginRequest(BaseModel):
    # `username` so FastAPI's OAuth2PasswordRequestForm is a drop-in,
    # but we accept email, mobile, or national_id.
    identifier: str = Field(..., min_length=5, description="email / mobile / national_id")
    password: str


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: Literal["bearer"] = "bearer"
    access_expires_in_sec: int
    refresh_expires_in_sec: int


class RefreshRequest(BaseModel):
    refresh_token: str


class UserOut(BaseModel):
    id: int
    national_id: str
    mobile: str
    email: str
    full_name_ar: str | None
    full_name_en: str | None
    preferred_locale: str
    is_active: bool
    is_admin: bool
    disclaimer_accepted_at: datetime | None
    last_login_at: datetime | None
    has_active_subscription: bool

    model_config = {"from_attributes": True}


class DisclaimerAcceptance(BaseModel):
    disclaimer_version: str = Field(..., description="Version string of the disclaimer being accepted.")


class DisclaimerOut(BaseModel):
    version: str
    body_ar: str
    body_en: str

    model_config = {"from_attributes": True}
