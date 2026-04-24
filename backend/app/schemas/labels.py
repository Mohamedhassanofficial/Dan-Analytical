"""Pydantic schemas for the ui_labels API."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class UiLabelOut(BaseModel):
    key: str
    label_ar: str
    label_en: str
    description_ar: str | None = None
    description_en: str | None = None
    context: str | None = None
    updated_at: datetime

    model_config = {"from_attributes": True}


class UiLabelUpdate(BaseModel):
    label_ar: str | None = Field(None, description="New Arabic label; omit to leave unchanged.")
    label_en: str | None = Field(None, description="New English label; omit to leave unchanged.")
    description_ar: str | None = None
    description_en: str | None = None
