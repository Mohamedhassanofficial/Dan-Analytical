"""
Seed `disclaimer_versions` with a default v1 (bilingual). Idempotent.

Usage (from backend/):
    python -m scripts.seed_disclaimer
"""
from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy import update
from sqlalchemy.dialects.postgresql import insert as pg_insert

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.models import DisclaimerVersion  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402

VERSION = "v1.0-2026-04"

BODY_AR = """\
إخلاء مسؤولية

المنصة هذه توفّر أدوات تحليلية لمحاكاة المحافظ الاستثمارية بناء على بيانات
تاريخية من السوق السعودية (تداول) باستخدام نماذج مالية قياسية (نظرية المحفظة
الحديثة لماركويتز، ونموذج CAPM، ومقاييس القيمة المعرضة للخطر VaR).

النتائج عبارة عن محاكاة رياضية وليست توصية بالبيع أو الشراء، ولا تمثل ضماناً
لأداء مستقبلي. الاستثمار في الأسهم ينطوي على مخاطر فقدان رأس المال. ينبغي على
المستخدم استشارة مستشار مالي مرخّص قبل اتخاذ أي قرار استثماري.

بالضغط على زر الموافقة، فإنك تقرّ بقراءة هذا الإخلاء وفهم أنّ المسؤولية عن أي
قرار استثماري تقع على عاتقك وحدك.
"""

BODY_EN = """\
Disclaimer

This platform provides analytical tools for simulating investment portfolios
from historical Saudi market (Tadawul) data using standard financial models
(Markowitz Modern Portfolio Theory, CAPM, Value-at-Risk).

Results are mathematical simulations, NOT buy/sell recommendations, and do
NOT guarantee future performance. Investing in equities carries the risk of
capital loss. Users should consult a licensed financial advisor before making
any investment decision.

By clicking accept, you acknowledge that you have read this disclaimer and
that responsibility for any investment decision is entirely your own.
"""


def seed() -> None:
    with SessionLocal() as db:
        # Mark all existing versions inactive, then upsert v1 as active.
        db.execute(update(DisclaimerVersion).values(is_active=False))
        stmt = pg_insert(DisclaimerVersion).values(
            version=VERSION,
            body_ar=BODY_AR,
            body_en=BODY_EN,
            is_active=True,
        ).on_conflict_do_update(
            index_elements=["version"],
            set_=dict(body_ar=BODY_AR, body_en=BODY_EN, is_active=True),
        )
        db.execute(stmt)
        db.commit()
    print(f"✓ Disclaimer {VERSION} is now active.")


if __name__ == "__main__":
    seed()
