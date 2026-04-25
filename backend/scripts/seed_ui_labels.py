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

    # ── Portfolios (Loay slide 1) ───────────────────────────────────────
    ("portfolios.title",              "المحافظ الاستثمارية",                 "Investment Portfolios",        "portfolios", None),
    ("portfolios.breadcrumb_home",    "الرئيسية",                             "Home",                         "portfolios", None),
    ("portfolios.breadcrumb_all",     "كافة المحافظ الاستثمارية",             "All Investment Portfolios",    "portfolios", None),
    ("portfolios.create_btn",         "إنشاء محفظة استثمارية جديدة",          "Create new portfolio",         "portfolios", None),
    ("portfolios.search_placeholder", "البحث في المحافظ الاستثمارية",         "Search portfolios",            "portfolios", None),
    ("portfolios.status_all",         "الكل",                                 "All",                          "portfolios", None),
    ("portfolios.status_active",      "فعّال",                                "Active",                       "portfolios", None),
    ("portfolios.status_inactive",    "غير فعّال",                            "Inactive",                     "portfolios", None),
    ("portfolios.col_name",           "الاسم",                                "Name",                         "portfolios", None),
    ("portfolios.col_select",         "اختيار محفظة الأسهم",                  "Select Stocks",                "portfolios", None),
    ("portfolios.col_details",        "تفاصيل محفظة الأسهم",                  "Portfolio Details",            "portfolios", None),
    ("portfolios.col_amount",         "مبلغ الاستثمار",                       "Investment Amount",            "portfolios", None),
    ("portfolios.col_status",         "الحالة",                               "Status",                       "portfolios", None),
    ("portfolios.col_actions",        "الاجراءات",                            "Actions",                      "portfolios", None),
    ("portfolios.action_edit",        "تعديل",                                "Edit",                         "portfolios", None),
    ("portfolios.action_delete",      "حذف",                                  "Delete",                       "portfolios", None),
    ("portfolios.modal_create_title", "إنشاء محفظة جديدة",                    "New Portfolio",                "portfolios", None),
    ("portfolios.modal_edit_title",   "تعديل محفظة",                          "Edit Portfolio",               "portfolios", None),
    ("portfolios.field_name",         "اسم المحفظة",                          "Portfolio Name",               "portfolios", None),
    ("portfolios.field_name_example", "مثال: محفظة نمو / محفظة توزيعات",      "e.g. Growth / Dividends",      "portfolios", None),
    ("portfolios.field_amount",       "مبلغ الاستثمار",                       "Investment Amount",            "portfolios", None),
    ("portfolios.field_amount_example", "مثال: 10000",                        "e.g. 10000",                   "portfolios", None),
    ("portfolios.create_submit",      "إنشاء",                                "Create",                       "portfolios", None),
    ("portfolios.save_submit",        "حفظ",                                  "Save",                         "portfolios", None),
    ("portfolios.cancel_btn",         "إلغاء",                                "Cancel",                       "portfolios", None),
    ("portfolios.confirm_delete_title", "تأكيد الحذف",                        "Confirm Delete",               "portfolios", None),
    ("portfolios.confirm_delete_body", "هل أنت متأكد من حذف هذه المحفظة؟ لا يمكن التراجع.",
                                      "Are you sure you want to delete this portfolio? This cannot be undone.",
                                                                              "portfolios", None),
    ("portfolios.empty_title",        "لا توجد محافظ بعد",                    "No portfolios yet",            "portfolios", None),
    ("portfolios.empty_cta",          "ابدأ بإنشاء محفظة استثمارية جديدة",    "Start by creating a new portfolio", "portfolios", None),
    ("portfolios.warn_recompute",     "تم تغيير مبلغ الاستثمار — يجب إعادة احتساب أوزان المحفظة من شاشة تفاصيل المحفظة",
                                      "Investment amount changed — please recompute the portfolio weights from the details screen",
                                                                              "portfolios",
                                      "Shown after a PATCH that returns needs_recompute=true"),
    ("portfolios.details_coming_soon","شاشة تفاصيل المحفظة قيد التطوير",      "Portfolio details screen is coming soon", "portfolios", None),

    # ── Screener portfolio-context banner (slide #6 wiring) ────────────
    ("screener.portfolio_context_label", "إضافة أسهم إلى محفظة:",            "Adding stocks to portfolio:",  "screener", None),
    ("screener.portfolio_context_count", "{{n}} أسهم في المحفظة",            "{{n}} stocks in portfolio",    "screener", "Keep {{n}} placeholder."),
    ("screener.portfolio_context_back",  "العودة لتفاصيل المحفظة",            "Back to portfolio details",    "screener", None),

    # ── Portfolio Details (slide #19) ──────────────────────────────────
    ("details.breadcrumb",        "تفاصيل المحفظة واحتساب الأوزان",         "Portfolio details & weight computation", "details", None),
    ("details.add_stocks",        "إضافة أسهم",                             "Add stocks",                    "details", None),
    ("details.compute_btn",       "احتساب الأوزان",                         "Compute weights",               "details", None),
    ("details.compute_needs_2",   "تحتاج لسهمين على الأقل قبل الاحتساب",     "Needs at least 2 holdings",     "details", None),
    ("details.compute_hint",      "اضغط على \"احتساب الأوزان\" لتشغيل خوارزمية ماركويتز وتفعيل المحفظة",
                                  "Click 'Compute weights' to run the Markowitz optimizer and activate the portfolio",
                                                                            "details", None),
    ("details.stat_amount",       "مبلغ الاستثمار",                         "Investment Amount",             "details", None),
    ("details.stat_holdings",     "عدد الأسهم",                             "Holdings",                      "details", None),
    ("details.stat_status",       "الحالة",                                 "Status",                        "details", None),
    ("details.stat_total_weight", "مجموع الأوزان",                          "Total Weight",                  "details", None),
    ("details.col_symbol",        "الرمز",                                  "Symbol",                        "details", None),
    ("details.col_weight",        "الوزن",                                  "Weight",                        "details", None),
    ("details.col_position_amount","قيمة المركز",                           "Position Amount",               "details", None),
    ("details.empty_title",       "لا توجد أسهم بعد",                       "No holdings yet",               "details", None),
    ("details.empty_cta",         "اضغط 'إضافة أسهم' لاختيار أسهم من السوق",  "Click 'Add stocks' to pick from the market", "details", None),

    # ── Sector averages (Loay slide 83 — احتساب متوسط أداء القطاع) ──────
    ("sector_avg.title",        "متوسط أداء القطاع",                  "Sector Performance Average",   "sector_avg", None),
    ("sector_avg.subtitle",     "اختر قطاع لعرض متوسطات مؤشراته",     "Pick a sector to view its indicator averages", "sector_avg", None),
    ("sector_avg.pick_sector",  "اختر القطاع…",                       "Choose a sector…",             "sector_avg", None),
    ("sector_avg.count_suffix", "عددها {{n}}",                        "{{n}} stocks",                 "sector_avg", "Keep {{n}} placeholder."),
    ("sector_avg.btn_risk",     "متوسطات مؤشرات المخاطر",             "Risk Indicator Averages",      "sector_avg", None),
    ("sector_avg.btn_financial","متوسطات المؤشرات المالية",           "Financial Indicator Averages", "sector_avg", None),
    ("sector_avg.refresh",      "تحديث",                              "Refresh",                      "sector_avg", None),
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
