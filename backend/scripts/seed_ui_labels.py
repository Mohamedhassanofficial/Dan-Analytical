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

from sqlalchemy import text
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
    ("screener.summary",
        "تضم سوق الأسهم السعودية (تداول) حاليًا {{total}} شركة مدرجة — آخر تاريخ لتحديث أسعار الأسهم: {{updated}}",
        "The Saudi Exchange (Tadawul) currently lists {{total}} companies — Last price update: {{updated}}",
        "screener",
        "Header strip per Loay slide 2. {{total}} = full universe count (auto-derived from /stocks); {{updated}} = ISO date+time of the newest last_price_date in the table, or '—' when none."),
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
    # Group-header bands above the column titles (Loay slide 4)
    ("screener.group_risk",         "تحليل مؤشرات المخاطر",         "Risk Measurement Ratios", "screener", None),
    ("screener.group_financial",    "تحليل النسب المالية",           "Financial Ratios",        "screener", None),
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

    # ── Navigation (Loay slide 2 — 7 sidebar items + admin) ─────────────
    ("nav.home",              "الرئيسية",                              "Home",                                       "nav", None),
    ("nav.tadawul_link",      "رابط سوق تداول",                        "Tadawul Market Link",                        "nav", None),
    ("nav.portfolios_view",   "عرض المحافظ الاستثمارية",               "View Investment Portfolios",                 "nav", None),
    ("nav.stock_indicators",  "المؤشرات الإرشادية لاختيار السهم المناسب", "Indicators for Selecting the Right Stock", "nav", None),
    ("nav.financial_ratios",  "تحليل النسب المالية الرئيسية",          "Main Financial Ratios Analysis",             "nav", None),
    ("nav.about_owner",       "لمحة مختصرة عن المالك",                  "Brief about the Owner",                      "nav", None),
    ("nav.info_dashboard",    "لوحة تحكم المعلومات",                   "Information Dashboard",                      "nav", None),
    ("nav.admin",             "إدارة النظام",                          "System Admin",                               "nav", None),
    # Legacy keys still referenced by older pages — kept until those pages refactor.
    ("nav.markets",           "الأسواق",                                "Markets",                                    "nav", None),
    ("nav.stocks",            "الأسهم",                                 "Stocks",                                     "nav", None),
    ("nav.portfolios",        "المحافظ",                                "Portfolios",                                 "nav", None),
    ("nav.education",         "التعليم",                                "Education",                                  "nav", None),
    ("nav.about",             "عن المالك",                              "About",                                      "nav", None),
    ("nav.screener",          "فلترة الأسهم",                          "Stock Screener",                             "nav", None),
    ("nav.dashboard",         "اللوحة الرئيسية",                       "Dashboard",                                  "nav", None),
    ("nav.optimize",          "تحسين المحفظة",                         "Optimize",                                   "nav", None),
    ("nav.history",           "سجل العمليات",                          "Run History",                                "nav", None),

    # ── Home / 3-card landing (Loay slide 2) ────────────────────────────
    ("home.welcome_back",   "مرحباً بعودتك إلى منصة التحكم",
                            "Welcome back to the control panel",            "home", None),
    ("home.admin_info",     "مرحبا {{name}} · لوحة المعلومات",
                            "Welcome {{name}} · Information panel",         "home",
                            "Keep {{name}} placeholder."),
    ("home.info_strip",
        "في جميع شاشات هذا التطبيق الإلكتروني تشير علامة [i] إلى توفر شرح تفصيلي لخطوات إنشاء محفظة استثمارية، بالإضافة إلى شرح المؤشرات التحليلية، وذلك لمساعدة المستخدم على فهم كيفية استخدام الأدوات التحليلية المدمجة في هذا التطبيق الإلكتروني بما يسهم في تحسين عائد المحفظة الاستثمارية التجريبية التي قام بإنشائها من خلال هذا التطبيق الإلكتروني.",
        "Throughout this application, the [i] icon signals an inline explainer for the screen and its analytical indicators — to help you understand the tools and improve the return of the experimental portfolio you build here.",
        "home", None),
    ("home.card1_title",    "إنشاء محفظة استثمارية وعرض المحافظ القائمة",
                            "Create a portfolio and view existing ones",    "home", None),
    ("home.card1_desc",     "عرض تفاصيل أسهم المحفظة.",
                            "Browse the holdings of any saved portfolio.",  "home", None),
    ("home.card1_explainer","ابدأ من هنا لإنشاء محفظة استثمارية جديدة باسم ومبلغ، أو لتعديل/حذف محافظك القائمة.",
                            "Start here to create a new portfolio with a name and amount, or edit/delete an existing one.",
                            "home", None),
    ("home.card2_title",    "عرض تحليل أداء الأسهم واختيار أسهم المحفظة الاستثمارية",
                            "Analyse stock performance & select portfolio stocks",
                            "home", None),
    ("home.card2_desc",     "عرض وتحليل أداء الأسهم ثم اختيار الأسهم المطلوبة للمحفظة.",
                            "Review stock performance, then add the ones you want to your portfolio.",
                            "home", None),
    ("home.card2_explainer","يفتح شاشة الـ Screener — 14 مؤشر مالي ومخاطر لكل سهم + فلاتر مالية وفلاتر مخاطر مستقلة.",
                            "Opens the Screener — 14 financial + risk indicators per stock with two independent filter groups.",
                            "home", None),
    ("home.card3_title",    "تفاصيل المحفظة الاستثمارية واحتساب أوزان الأسهم وتقييم مخاطرها وأدائها ومراقبة خسائر الأسهم",
                            "Portfolio details, compute weights, assess risk + monitor losses",
                            "home", None),
    ("home.card3_desc",     "احتساب أوزان الأسهم حسب النموذج وعرض تفاصيل المحفظة.",
                            "Run the Markowitz weights and review the portfolio details.",
                            "home", None),
    ("home.card3_explainer","ادخل من هنا إلى شاشة المحفظة، اضغط 'احتساب الأوزان' لتشغيل خوارزمية ماركويتز، وراجع Sharpe / العائد المتوقع / التذبذب لكل سهم.",
                            "Enter the portfolio screen, click 'Compute weights' to run the Markowitz solver, then review Sharpe / expected return / volatility per holding.",
                            "home", None),
    ("home.open_button",    "فتح",                                "Open",                          "home", None),
    ("home.footer_version", "Dan Analytical 2026 © v2.0",         "Dan Analytical 2026 © v2.0",    "home", None),
    ("home.quick_links",    "روابط سريعة",                        "Quick links",                   "home", None),

    # ── Placeholder pages (Loay slide 2 sidebar items not yet built) ───
    ("markets.title",       "الأسواق",                            "Markets",                       "placeholder", None),
    ("markets.coming_soon", "قريباً — شاشة الأسواق قيد التطوير.",
                            "Coming soon — Markets screen is under development.",
                            "placeholder", None),
    ("education.title",     "التعليم",                            "Education",                     "placeholder", None),
    ("education.coming_soon","قريباً — مركز التعليم والشروحات قيد التطوير.",
                            "Coming soon — Education centre is under development.",
                            "placeholder", None),
    ("about.title",         "عن المالك",                          "About the owner",               "placeholder", None),
    ("about.coming_soon",   "قريباً — صفحة 'عن المالك' قيد التطوير.",
                            "Coming soon — About-the-owner page is under development.",
                            "placeholder", None),

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

    # ── Screener Add modal (Loay slide #7) ──────────────────────────────
    ("screener.add_modal_title",         "إضافة سهم إلى المحفظة",             "Add stock to portfolio",       "screener", None),
    ("screener.add_modal_stock",         "السهم",                             "Stock",                        "screener", None),
    ("screener.add_modal_portfolio",     "المحفظة",                           "Portfolio",                    "screener", None),
    ("screener.add_modal_holdings",      "{{n}} أسهم · {{amount}}",           "{{n}} stocks · {{amount}}",    "screener", "Keep {{n}} and {{amount}} placeholders."),
    ("screener.add_modal_weight_notice", "سيتم تصفير أوزان المحفظة بعد الإضافة. يجب إعادة احتساب الأوزان من شاشة تفاصيل المحفظة.",
                                         "Portfolio weights will reset to zero after adding. Recompute the weights from the portfolio details screen.",
                                                                              "screener", None),
    ("screener.add_modal_confirm",       "تأكيد الإضافة",                     "Confirm Add",                  "screener", None),
    ("screener.add_modal_cancel",        "إلغاء",                             "Cancel",                       "screener", None),
    ("screener.add_modal_added",         "تمت إضافة {{ticker}} إلى المحفظة",  "Added {{ticker}} to portfolio", "screener", "Keep {{ticker}} placeholder."),

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
    ("sector_avg.title_bar",    "احتساب متوسط أداء القطاع الصناعي",   "Industry Sector Performance Averages", "sector_avg", None),
    ("sector_avg.btn_calculate","احتساب",                             "Calculate",                    "sector_avg", None),
    ("sector_avg.count_chip",   "{{name}} – عددها {{n}}",             "{{name}} – {{n}} stocks",      "sector_avg", "Keep {{name}} and {{n}} placeholders."),

    # ── (i) tooltip AR/EN toggle (Loay slide 5) ─────────────────────────
    ("tooltip.lang_ar",         "العربية",                            "Arabic",                       "tooltip", None),
    ("tooltip.lang_en",         "English",                            "English",                      "tooltip", None),

    # ── Filter modal help banner (Loay slide 6) ─────────────────────────
    ("filter_modal.help_title", "كيفية استخدام الفلاتر",              "How to use the filters",       "screener", None),
    ("filter_modal.help_body",
        "اختر المؤشر الذي تريد التصفية من خلاله، ويمكنك اختيار أكثر من مؤشر في نفس الوقت.",
        "Pick the indicator you want to filter by — you can pick more than one at the same time.",
        "screener", None),

    # ── Stock Analyze page (Loay slides 98-99 / 109-111) ────────────────
    ("analyze.title",            "تحليل أداء السهم",                  "Stock Analysis",                "analyze", None),
    ("analyze.back_btn",         "العودة لشاشة الـ Screener",         "Back to Screener",              "analyze", None),
    ("analyze.section_movement", "حركة السهم",                        "Stock Movement",                "analyze", None),
    ("analyze.section_risk",     "مؤشرات قياس مخاطر السهم",          "Stock Risk Measurement",        "analyze", None),
    ("analyze.section_financial","النسب المالية الرئيسية",             "Stock Performance (Key Financial Ratios)", "analyze", None),
    ("analyze.section_extras",   "نسب مالية موسّعة",                   "Extended Financial Ratios",     "analyze", None),
    ("analyze.section_dates",    "تواريخ الإفصاحات المالية",           "Financial Statements Issuance Dates", "analyze", None),
    ("analyze.section_capm",     "العائد المتوقع (نموذج CAPM)",       "Expected Stock Return (CAPM Model)", "analyze", None),
    ("analyze.section_var",      "القيمة المعرضة للخطر (VaR)",         "Expected Stock VaR",            "analyze", None),
    ("analyze.section_charts",   "الرسوم البيانية",                    "Chart Analysis",                "analyze", None),
    ("analyze.field_market_price","السعر السوقي",                      "Market Price",                  "analyze", None),
    ("analyze.field_avg_midpoint","متوسط منتصف السعر",                  "Avg Price Midpoint",            "analyze", None),
    ("analyze.field_52w_high",   "أعلى سعر في 52 أسبوع",              "52 Week High",                  "analyze", None),
    ("analyze.field_52w_low",    "أدنى سعر في 52 أسبوع",              "52 Week Low",                   "analyze", None),
    ("analyze.field_min_return", "أدنى عائد يومي خلال 250 يوم تداول", "Min Daily Return (250 days)",   "analyze", None),
    ("analyze.field_max_return", "أعلى عائد يومي خلال 250 يوم تداول", "Max Daily Return (250 days)",   "analyze", None),
    ("analyze.field_support",    "خط الدعم",                           "Support Price",                 "analyze", None),
    ("analyze.field_resistance", "خط المقاومة",                        "Resistance Price",              "analyze", None),
    ("analyze.field_midpoint",   "منتصف الدعم/المقاومة",               "Support/Resistance Midpoint",   "analyze", None),
    ("analyze.expected_annual",  "العائد السنوي المتوقع",              "Expected Annual Return",        "analyze", None),
    ("analyze.expected_daily",   "العائد اليومي المتوقع",              "Expected Daily Return",         "analyze", None),
    ("analyze.var_days_label",   "عدد أيام VaR",                       "VaR window (days)",             "analyze", None),
    ("analyze.var_loss_amount",  "أقصى خسارة متوقعة (ريال)",          "Maximum Expected Loss (SAR)",   "analyze", None),
    ("analyze.chart_distribution","التوزيع الاحتمالي لعوائد السهم",     "Probability Distribution of Stock Returns", "analyze", None),
    ("analyze.chart_stock_vs_index","العائد اليومي للسهم مقابل المؤشر","Stock vs Index Daily Return",   "analyze", None),
    ("analyze.chart_support_resistance","تحليل الدعم والمقاومة (آخر 30 يوم)", "Support and Resistance (Last 30 Days)", "analyze", None),
    # 16 extended-ratio column labels (Loay slide 79)
    ("ratio.current_ratio",      "نسبة السيولة الجارية",               "Current Ratio",                 "ratio", None),
    ("ratio.quick_ratio",        "نسبة السيولة السريعة",               "Quick Ratio",                   "ratio", None),
    ("ratio.cash_ratio",         "نسبة السيولة النقدية",               "Cash Ratio",                    "ratio", None),
    ("ratio.interest_coverage",  "نسبة تغطية الفوائد",                 "Interest Coverage Ratio",       "ratio", None),
    ("ratio.asset_turnover",     "دوران الأصول",                       "Asset Turnover",                "ratio", None),
    ("ratio.inventory_turnover", "دوران المخزون",                      "Inventory Turnover",            "ratio", None),
    ("ratio.receivables_turnover","دوران الذمم المدينة",               "Receivables Turnover",          "ratio", None),
    ("ratio.payables_turnover",  "دوران الذمم الدائنة",                "Payables Turnover",             "ratio", None),
    ("ratio.roa",                "العائد على الأصول",                  "Return on Assets (ROA)",        "ratio", None),
    ("ratio.net_profit_margin",  "هامش الربح الصافي",                  "Net Profit Margin",             "ratio", None),
    ("ratio.gross_profit_margin","الهامش الإجمالي",                    "Gross Profit Margin",           "ratio", None),
    ("ratio.bvps",               "القيمة الدفترية للسهم",              "Book Value Per Share (BVPS)",   "ratio", None),
    ("ratio.revenue_per_share",  "إيرادات السهم",                      "Revenue Per Share",             "ratio", None),
    ("ratio.debt_to_market_cap", "الدين إلى القيمة السوقية",           "Total Debt / Market Cap",       "ratio", None),
    ("ratio.cash_to_assets",     "النقد وما يعادله / الأصول",          "Cash & Equivalents / Total Assets", "ratio", None),
    ("ratio.receivables_to_assets","الذمم المدينة / الأصول",           "Cash & Receivables / Total Assets", "ratio", None),

    # ── Add-to-portfolio modal redesign (Loay slide 8) ──────────────────
    ("screener.add_modal_subtitle",
                                "اسم السهم",                          "Stock name",                   "screener", None),
    ("screener.add_modal_field_stock",
                                "السهم",                              "Stock",                        "screener", None),
    ("screener.add_modal_field_portfolio",
                                "اختر المحفظة",                       "Choose portfolio",             "screener", None),
    ("screener.add_modal_portfolio_option",
                                "{{name}}  مبلغ الاستثمار {{amount}}",
                                "{{name}}  Investment {{amount}}",    "screener",
                                "Keep {{name}} and {{amount}} placeholders."),
    ("screener.add_modal_field_date",
                                "تاريخ الشراء",                       "Purchase date",                "screener", None),
    ("screener.add_modal_field_price",
                                "سعر الشراء (﷼)",                     "Purchase price (SAR)",         "screener", None),
    ("screener.add_modal_no_portfolios",
                                "ليس لديك محافظ بعد. اضغط هنا لإنشاء محفظة جديدة.",
                                "You don't have any portfolios yet. Click here to create one.",
                                "screener", None),

    # ── Disclosure-date columns (Loay slide — Financial Ratios band) ───
    ("screener.col_balance_sheet_date",
                                  "آخر تحديث للميزانية العمومية",
                                  "Last Updated Balance Sheet",         "screener", None),
    ("screener.col_income_statement_date",
                                  "آخر تحديث لقائمة الدخل",
                                  "Last Updated Income Statement",      "screener", None),
    ("screener.col_dividend_date",
                                  "تاريخ آخر توزيع نقدي",
                                  "Latest Dividend Date",               "screener", None),

    # ── Data sources & update periods footer ───────────────────────────
    ("data_sources.title",
                                  "مصادر البيانات وفترات التحديث",
                                  "Data Sources & Update Periods",      "screener", None),
    ("data_sources.card_stock_prices_title",
                                  "تاريخ تحديث أسعار الأسهم التاريخية على مدى ثلاث سنوات",
                                  "Historical stock prices — last 3 years",
                                                                        "screener", None),
    ("data_sources.card_sector_indices_title",
                                  "تاريخ تحديث أسعار مؤشرات القطاعات لأسهم تداول على مدى عشر سنوات",
                                  "Sector index prices (Tadawul) — last 10 years",
                                                                        "screener", None),
    ("data_sources.card_last_update_title",
                                  "آخر تاريخ لتحديث أسعار الأسهم",
                                  "Most recent stock price update",     "screener", None),
    ("data_sources.from_to",      "من {{from}} إلى {{to}}",            "From {{from}} To {{to}}",      "screener", "Keep {{from}} and {{to}} placeholders."),
    ("data_sources.data_source_label", "مصدر البيانات",                "Data Source",                  "screener", None),
]


# Long bilingual descriptions for the 14 indicator column headers — surfaced
# as (i) tooltips next to each column. Backfilled separately because they
# weren't part of the original LABELS tuple (which only carries description_en).
# Idempotent: the seed code below only fills NULL columns, so admin edits stay.
INDICATOR_DESCRIPTIONS: list[tuple[str, str, str]] = [
    # (key, description_ar, description_en)
    ("screener.col_beta",
     "حساسية السهم لتقلبات السوق — قيمة 1.0 تعني تذبذبًا مساويًا للسوق، أعلى من 1 أكثر تذبذبًا.",
     "Sensitivity of the stock's returns to market movements — 1.0 means the stock moves in line with the market."),
    ("screener.col_capm_return",
     "العائد المتوقع وفق نموذج CAPM = العائد الخالي من المخاطر + بيتا × علاوة مخاطر السوق.",
     "Expected return from the CAPM model: risk-free rate + beta × market risk premium."),
    ("screener.col_daily_vol",
     "الانحراف المعياري للعوائد اليومية — مقياس للتذبذب على المدى القصير.",
     "Standard deviation of daily returns — short-term volatility."),
    ("screener.col_annual_vol",
     "التذبذب السنوي = التذبذب اليومي × جذر 252 — المدخل الأساسي لتصنيف المخاطر.",
     "Daily volatility × √252 — drives the Risk Ranking categorisation."),
    ("screener.col_sharp",
     "(العائد − معدل خالي المخاطر) ÷ التذبذب — يقيس كفاءة العائد مقابل المخاطرة.",
     "(Return − risk-free rate) / volatility — measures return per unit of risk."),
    ("screener.col_var_1d",
     "أقصى خسارة متوقعة في يوم واحد عند مستوى ثقة 95% (Value at Risk).",
     "Worst expected loss over a single day at 95% confidence (Value at Risk)."),
    ("screener.col_risk_rank",
     "تصنيف كمي للمخاطر مشتق من التذبذب السنوي وفق عتبات شريحة 105: متحفظ / متحفظ معتدل / جريء / جريء جداً.",
     "Risk category derived from annual volatility per slide-105 thresholds: Conservative, Moderately Conservative, Aggressive, Very Aggressive."),
    ("screener.col_pe",
     "السعر ÷ ربحية السهم — ما يدفعه المستثمر مقابل ريال واحد من الأرباح.",
     "Price ÷ earnings per share — what an investor pays per riyal of earnings."),
    ("screener.col_mb",
     "السعر السوقي ÷ القيمة الدفترية للسهم — المضاعف على صافي حقوق المساهمين.",
     "Market price ÷ book value per share — the multiple on shareholder equity."),
    ("screener.col_roe",
     "صافي الربح ÷ حقوق المساهمين — كفاءة الإدارة في توليد الأرباح من رأس المال.",
     "Net income ÷ shareholder equity — how efficiently management converts equity to profit."),
    ("screener.col_fcf",
     "التدفق النقدي الحر ÷ القيمة السوقية — مقياس لجودة الأرباح النقدية.",
     "Free cash flow ÷ market cap — quality of cash earnings."),
    ("screener.col_leverage",
     "إجمالي الديون ÷ حقوق المساهمين — مستوى اعتماد الشركة على الدين في تمويل عملياتها.",
     "Total debt ÷ shareholder equity — how much the company relies on debt financing."),
    ("screener.col_eps",
     "صافي الربح ÷ عدد الأسهم — حصة السهم الواحد من الأرباح.",
     "Net income ÷ shares outstanding — earnings per share."),
    ("screener.col_div_yield",
     "التوزيع السنوي ÷ السعر — العائد النقدي السنوي للمساهم.",
     "Annual dividend ÷ price — the annual cash yield to shareholders."),
    ("screener.col_div_rate",
     "إجمالي التوزيع النقدي السنوي للسهم الواحد بالريال.",
     "Total annual dividend paid per share, in SAR."),
    ("screener.col_balance_sheet_date",
     "تاريخ آخر ميزانية عمومية أفصحت عنها الشركة.",
     "Date of the most recently disclosed balance sheet."),
    ("screener.col_income_statement_date",
     "تاريخ آخر قائمة دخل أفصحت عنها الشركة.",
     "Date of the most recently disclosed income statement."),
    ("screener.col_dividend_date",
     "تاريخ آخر توزيع نقدي تمت الموافقة عليه (يكون قبل تاريخ الاستحقاق).",
     "Date of the most recently approved cash dividend."),
    # Home cards (Loay slide #2) — the (i) icon on each card pulls these.
    ("home.card1_explainer",
     "ابدأ من هنا لإنشاء محفظة استثمارية جديدة باسم ومبلغ، أو لتعديل/حذف محافظك القائمة.",
     "Start here to create a new portfolio with a name and amount, or edit/delete an existing one."),
    ("home.card2_explainer",
     "يفتح شاشة الـ Screener — 14 مؤشر مالي ومخاطر لكل سهم + فلاتر مالية وفلاتر مخاطر مستقلة.",
     "Opens the Screener — 14 financial + risk indicators per stock with two independent filter groups."),
    ("home.card3_explainer",
     "ادخل من هنا إلى شاشة المحفظة، اضغط 'احتساب الأوزان' لتشغيل خوارزمية ماركويتز، وراجع Sharpe / العائد المتوقع / التذبذب لكل سهم.",
     "Enter the portfolio screen, click 'Compute weights' to run the Markowitz solver, then review Sharpe / expected return / volatility per holding."),
    # 16 extended-ratio descriptions (Loay slide 79)
    ("ratio.current_ratio",
     "الأصول المتداولة ÷ الالتزامات المتداولة — قدرة الشركة على سداد التزاماتها قصيرة الأجل. القيمة المثالية 1.5–2.0.",
     "Current Assets ÷ Current Liabilities — ability to cover short-term obligations. Ideal range 1.5–2.0."),
    ("ratio.quick_ratio",
     "(الأصول المتداولة − المخزون) ÷ الالتزامات المتداولة — السيولة الفورية بدون الاعتماد على بيع المخزون. أعلى من 1 = جيد.",
     "(Current Assets − Inventory) ÷ Current Liabilities — immediate liquidity without selling inventory. Above 1 is healthy."),
    ("ratio.cash_ratio",
     "النقد وما يعادله ÷ الالتزامات المتداولة — أكثر مقاييس السيولة تحفظًا. القيمة المثالية 0.5–1.0.",
     "Cash & Equivalents ÷ Current Liabilities — the most conservative liquidity measure. Healthy range 0.5–1.0."),
    ("ratio.interest_coverage",
     "الأرباح قبل الفوائد والضرائب ÷ مصروف الفوائد — قدرة الشركة على تغطية فوائد ديونها. أعلى من 3× مقبول.",
     "EBIT ÷ Interest Expense — how easily the company covers debt-interest. Above 3× is acceptable."),
    ("ratio.asset_turnover",
     "الإيرادات ÷ متوسط إجمالي الأصول — كفاءة الشركة في توليد إيرادات من أصولها. ارتفاع النسبة = كفاءة أعلى.",
     "Revenue ÷ Avg Total Assets — efficiency of generating sales from assets. Higher = more efficient."),
    ("ratio.inventory_turnover",
     "تكلفة البضاعة المباعة ÷ متوسط المخزون — عدد مرات تجديد المخزون سنويًا. مرتفع لتجارة التجزئة، صفر للبنوك.",
     "COGS ÷ Avg Inventory — how often inventory is sold and replaced per year. High for retail, zero for banks."),
    ("ratio.receivables_turnover",
     "الإيرادات الآجلة ÷ متوسط الذمم المدينة — سرعة تحصيل المستحقات من العملاء.",
     "Credit Sales ÷ Avg Receivables — speed of collecting customer payments."),
    ("ratio.payables_turnover",
     "المشتريات ÷ متوسط الذمم الدائنة — سرعة سداد الموردين.",
     "Purchases ÷ Avg Payables — speed of paying suppliers."),
    ("ratio.roa",
     "صافي الربح ÷ إجمالي الأصول — كفاءة الشركة في توليد أرباح من كامل أصولها (وليس فقط حقوق الملكية).",
     "Net Income ÷ Total Assets — efficiency of generating profit from the full asset base (not just equity)."),
    ("ratio.net_profit_margin",
     "صافي الربح ÷ الإيرادات — نسبة ما يبقى من كل ريال إيرادات بعد كل المصروفات والضرائب.",
     "Net Income ÷ Revenue — share of every revenue riyal that remains as profit after all costs."),
    ("ratio.gross_profit_margin",
     "(الإيرادات − تكلفة البضاعة المباعة) ÷ الإيرادات — هامش الربح من النشاط الأساسي قبل المصروفات الإدارية.",
     "(Revenue − COGS) ÷ Revenue — core operating margin before SG&A."),
    ("ratio.bvps",
     "حقوق المساهمين ÷ عدد الأسهم القائمة — صافي القيمة الدفترية لكل سهم.",
     "Shareholders' Equity ÷ Shares Outstanding — net book value attributable to each share."),
    ("ratio.revenue_per_share",
     "الإيرادات السنوية ÷ عدد الأسهم القائمة — حصة السهم من الإيرادات (مفيدة لمقارنة الشركات الخاسرة).",
     "Annual Revenue ÷ Shares Outstanding — per-share revenue (useful when comparing loss-making firms)."),
    ("ratio.debt_to_market_cap",
     "إجمالي الديون ÷ القيمة السوقية — معيار التوافق مع الشريعة الإسلامية. أقل من 33% يُعتبر مقبولًا شرعيًا.",
     "Total Debt ÷ Market Capitalization — Shariah-compliance metric. Below 33% is acceptable."),
    ("ratio.cash_to_assets",
     "النقد وما يعادله ÷ إجمالي الأصول — معيار توافق شرعي إضافي للسيولة الفائضة.",
     "Cash & Equivalents ÷ Total Assets — additional Shariah liquidity-coverage metric."),
    ("ratio.receivables_to_assets",
     "الذمم المدينة ÷ إجمالي الأصول — معيار التوافق مع الشريعة الإسلامية لمستوى الذمم الآجلة.",
     "Receivables ÷ Total Assets — Shariah-compliance metric for credit-receivable exposure."),
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

        # Backfill long descriptions for indicator columns. Only writes when
        # the field is currently NULL — admin overrides are preserved.
        for key, desc_ar, desc_en in INDICATOR_DESCRIPTIONS:
            db.execute(
                text(
                    "UPDATE ui_labels SET description_ar = :v "
                    "WHERE key = :k AND description_ar IS NULL"
                ),
                {"v": desc_ar, "k": key},
            )
            db.execute(
                text(
                    "UPDATE ui_labels SET description_en = :v "
                    "WHERE key = :k AND description_en IS NULL"
                ),
                {"v": desc_en, "k": key},
            )
        db.commit()
    return len(LABELS)


if __name__ == "__main__":
    n = seed()
    print(f"✓ ui_labels seeded: {n} entries (existing entries preserved).")
