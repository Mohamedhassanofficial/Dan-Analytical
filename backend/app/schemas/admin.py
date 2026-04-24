"""Pydantic schemas for the admin API."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

ValueType = Literal["number", "string", "bool", "json"]


class AdminConfigOut(BaseModel):
    key: str
    value: Any
    value_type: ValueType
    description_ar: str | None = None
    description_en: str | None = None
    updated_at: datetime

    model_config = {"from_attributes": True}


class AdminConfigUpdate(BaseModel):
    value: Any = Field(..., description="New value. Coerced per value_type on the server.")


class SectorUploadResult(BaseModel):
    filename: str
    rows_seen: int
    rows_inserted: int
    rows_skipped: int
    warnings: list[str] = []
