"""
Seed `ui_labels` with the default strings admins are expected to be able to
rename / retranslate. Idempotent: re-runs only set values on first insert and
never overwrite admin edits.

Keys follow i18n-bundle convention: `<context>.<path>` — e.g. `screener.col_symbol`.
When the frontend boots, `LabelsContext` pulls the full table and layers
these on top of the static `src/i18n/{ar,en}.json` bundles.

Usage (from backend/):
    python -m scripts.seed_ui_labels
"""
from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy.dialects.postgresql import insert as pg_insert

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.models import UiLabel  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402


# (key, label_ar, label_en, context, description_en)
# Keep entries sorted by context then key for easier auditing.
LABELS: list[tuple[str, str, str, str, str | None]] = [
    # ── Screener (the filtering table) ──────────────────────────────────
    # Title changed 2026-04-24 to match PPTX slide 82.
    ("screener.title",              "تحليل أداء الأسهم واختيار أسهم المحفظة الاستثمارية",
                                    "Stock Performance Analysis & Portfolio Selection",       "screener", None),
    ("screener.summary",            "{{shown}} من إجمالي {{total}} شركة",
                                    "{{shown}} of {{total}} companies",                       "screener",
                                    "Header row count. Keep {{shown}} and {{total}} placeholders."),
    ("screener.last_update",        "آخر تحديث",                   "Last update",             "screener", None),
    ("screener.search_placeholder", "ابحث برمز السهم أو الاسم…",   "Search symbol or name…",  "screener", None),
    ("screener.clear_filters",      "مسح الفلاتر",                 "Clear filters",           "screener", None),
    ("screener.filter_any",         "الكل",                        "Any",                     "screener", None),
    # Column headers — identity
    ("screener.col_symbol",         "الرمز",                       "Symbol",                  "screener", None),
    ("screener.col_name",           "الشركة",                      "Company",                 "screener", None),
    ("screener.col_sector",         "القطاع",                      "Sector",                  "screener", None),
    ("screener.col_industry",       "النشاط",                      "Industry",                "screener", None),
    ("screener.col_actions",        "إجراءات",                     "Actions",                 "screener", None),
    # Column headers — Risk group (6 indicators + ranking)
    ("screener.col_beta",           "بيتا",                        "β",                       "screener", None),
    ("screener.col_capm_return",    "العائد المتوقع (CAPM)",      "Expected Return (CAPM)",  "screener", None),
    ("screener.col_daily_vol",      "التذبذب اليومي",              "Daily Volatility",        "screener", None),
    ("screener.col_annual_vol",     "التذبذب السنوي",              "Annual Volatility",       "screener", None),
    ("screener.col_sharp",          "نسبة شارب",                   "Sharp Ratio",             "screener", None),
    ("screener.col_var_1d",         "VaR (يوم)",                   "VaR (1 Day)",             "screener", None),
    ("screener.col_risk_rank",      "تصنيف المخاطر",               "Risk Ranking",            "screener", None),
    # Column headers — Financial group (8 indicators)
    ("screener.col_pe",             "مكرر الربحية (P/E)",          "P/E Ratio",               "screener", None),
    ("screener.col_mb",             "القيمة السوقية للدفترية (M/B)", "Market / Book",         "screener", None),
    ("screener.col_roe",            "العائد على حقوق الملكية (ROE)", "ROE",                   "screener", None),
    ("screener.col_fcf",            "عائد التدفق النقدي الحر",     "FCF Yield",               "screener", None),
    ("screener.col_leverage",       "نسبة الرفع المالي",           "Leverage Ratio",          "screener", None),
    ("screener.col_eps",            "ربحية السهم (EPS)",           "EPS",                     "screener", None),
    ("screener.col_div_yield",      "عائد التوزيعات",              "Dividend Yield",          "screener", None),
    ("screener.col_div_rate",       "معدل التوزيع السنوي",         "Annual Dividend Rate",    "screener", None),
    # Risk Ranking category labels (match DB enum values in Arabic/English)
    ("ranking.conservative",        "متحفظ",                       "Conservative",            "screener", None),
    ("ranking.moderate",            "متحفظ معتدل",                 "Moderately Conservative", "screener", None),
    ("ranking.aggressive",          "جريء",                        "Aggressive",              "screener", None),
    ("ranking.very_aggressive",     "جريء جداً",                   "Very Aggressive",         "screener", None),
    ("ranking.unknown",             "—",                           "—",                       "screener", None),
    # Filter modal strings
    ("screener.filter_risk_btn",    "فلتر مؤشرات المخاطر",         "Filter Risk Indicators",  "screener", None),
    ("screener.filter_financial_btn", "فلتر مؤشرات المالية",       "Filter Financial Indicators", "screener", None),
    ("screener.filter_risk_title",  "فلترة مؤشرات المخاطر",        "Risk Indicator Filter",   "screener", None),
    ("screener.filter_financial_title", "فلترة المؤشرات المالية",  "Financial Indicator Filter", "screener", None),
    ("screener.filter_indicator",   "المؤشر",                      "Indicator",               "screener", None),
    ("screener.filter_operator",    "المقارنة",                    "Operator",                "screener", None),
    ("screener.filter_value",       "القيمة",                      "Value",                   "screener", None),
    ("screener.filter_apply",       "تطبيق",                       "Apply",                   "screener", None),
    ("screener.filter_clear_group", "مسح المجموعة",                "Clear group",             "screener", None),
    # Per-row controls
    ("screener.add",                "إضافة",                       "Add",                     "screener", None),
    ("screener.added",              "مُضاف",                       "Added",                   "screener", None),
    ("screener.remove",             "إزالة من المسودة",            "Remove from draft",       "screener", None),
    ("screener.add_to_portfolio",   "إضافة إلى المحفظة المؤقتة",   "Add to draft portfolio",  "screener", None),
    ("screener.analyze",            "تحليل سهم",                   "Analyze",                 "screener", None),
    ("screener.empty",              "لا توجد شركات تطابق الفلاتر الحالية.",
                                    "No companies match the current filters.",                "screener", None),
    ("screener.draft_summary",      "{{n}} شركة في المحفظة المؤقتة",
                                    "{{n}} companies in draft portfolio",                     "screener",
                                    "Keep the {{n}} placeholder."),

    # ── Navigation ──────────────────────────────────────────────────────
    ("nav.screener",  "فلترة الأسهم",    "Stock Screener", "nav", None),
    ("nav.dashboard", "اللوحة الرئيسية", "Dashboard",      "nav", None),
    ("nav.optimize",  "تحسين المحفظة",   "Optimize",       "nav", None),
    ("nav.history",   "سجل العمليات",    "Run History",    "nav", None),
]


def seed() -> int:
    with SessionLocal() as db:
        for key, label_ar, label_en, context, desc_en in LABELS:
            stmt = pg_insert(UiLabel).values(
                key=key,
                label_ar=label_ar,
                label_en=label_en,
                description_en=desc_en,
                context=context,
            ).on_conflict_do_nothing(index_elements=["key"])
            # on_conflict_do_nothing → admin edits are preserved across re-runs.
            db.execute(stmt)
        db.commit()
    return len(LABELS)


if __name__ == "__main__":
    n = seed()
    print(f"✓ ui_labels seeded: {n} entries (existing entries preserved).")
