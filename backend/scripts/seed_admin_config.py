"""
Seed `admin_config` with platform defaults referenced throughout the PDF
brief. Admins can override any of these via the admin dashboard UI.

Usage (from backend/):
    python -m scripts.seed_admin_config
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from sqlalchemy.dialects.postgresql import insert as pg_insert

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import settings  # noqa: E402
from app.db.models import AdminConfig  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402

# (key, value, value_type, description_ar, description_en)
DEFAULTS: list[tuple[str, object, str, str, str]] = [
    (
        "risk_free_rate",
        settings.default_risk_free_rate,
        "number",
        "معدل الخالي من المخاطر (أذونات خزانة مؤسسة النقد SAMA)، سنوي كنسبة عشرية.",
        "Annual risk-free rate (SAMA treasury instruments), as a decimal.",
    ),
    (
        "lookback_days",
        settings.default_lookback_days,
        "number",
        "عدد أيام التداول المستخدمة لاحتساب العائدات والتباين المشترك.",
        "Trading-day window used to estimate returns and covariance.",
    ),
    (
        "trading_days_per_year",
        settings.trading_days_per_year,
        "number",
        "عدد أيام التداول السنوية المستخدمة في تحويل العوائد اليومية إلى سنوية.",
        "Trading days per year used to annualize daily statistics.",
    ),
    (
        "yfinance_refresh_hour_utc",
        settings.yfinance_refresh_hour_utc,
        "number",
        "ساعة التحديث اليومي لأسعار الأسهم من Yahoo Finance (بتوقيت UTC).",
        "Daily refresh hour for Yahoo Finance stock prices (UTC).",
    ),
    (
        "allow_shorting",
        False,
        "bool",
        "السماح بأوزان سالبة (البيع على المكشوف). الافتراضي معطّل حسب الشريحة 124.",
        "Allow negative weights (shorting). Disabled by default per slide 124.",
    ),
    (
        "default_confidence_var",
        0.95,
        "number",
        "مستوى الثقة الافتراضي لحساب القيمة المعرضة للخطر (VaR).",
        "Default confidence level used for Value-at-Risk calculations.",
    ),
    (
        "subscription_price_sar",
        settings.subscription_price_sar,
        "number",
        "سعر الاشتراك الشهري بالريال السعودي.",
        "Monthly subscription price in SAR.",
    ),
    (
        "subscription_duration_days",
        settings.subscription_duration_days,
        "number",
        "مدة الاشتراك بالأيام بعد الدفع الناجح.",
        "Subscription duration in days after a successful payment.",
    ),
    (
        "payment_gateway",
        settings.payment_gateway,
        "string",
        "بوابة الدفع النشطة: STC Pay أو PayTabs.",
        "Active payment gateway: STC Pay or PayTabs.",
    ),
    (
        "pdpl_data_region",
        settings.pdpl_data_region,
        "string",
        "إقليم تخزين البيانات (يجب أن يكون داخل المملكة حسب نظام PDPL).",
        "Data residency region (must be within KSA per PDPL).",
    ),
]


def seed() -> int:
    with SessionLocal() as db:
        count = 0
        for key, value, vtype, desc_ar, desc_en in DEFAULTS:
            stmt = pg_insert(AdminConfig).values(
                key=key,
                value=json.dumps(value),
                value_type=vtype,
                description_ar=desc_ar,
                description_en=desc_en,
            ).on_conflict_do_update(
                index_elements=["key"],
                set_=dict(
                    value_type=vtype,
                    description_ar=desc_ar,
                    description_en=desc_en,
                ),
                # Note: we do NOT overwrite `value` on conflict — admins may have
                # edited it in the UI and we should preserve their change.
            )
            db.execute(stmt)
            count += 1
        db.commit()
    return count


if __name__ == "__main__":
    n = seed()
    print(f"✓ admin_config defaults upserted: {n}")
