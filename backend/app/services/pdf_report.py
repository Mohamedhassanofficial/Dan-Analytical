"""
Bilingual PDF report exporter for portfolio optimization runs.

Layout (per PDF brief — "export evaluation and analysis reports in PDF"):
    1. Header with run id, timestamp, user locale
    2. Summary metrics: Sharpe, expected return, volatility, sum(w)
    3. Weights table (ticker, weight %)
    4. Risk contribution table (if available in run snapshot)
    5. Disclaimer footer

Arabic handling:
    - arabic_reshaper joins connected letters
    - python-bidi applies the Unicode bidi algorithm so text flows right-to-left
    - An Arabic-capable TTF must live at backend/assets/fonts/<PDF_ARABIC_FONT>
      (see assets/fonts/README.md). Without it, Arabic renders as empty boxes.
"""
from __future__ import annotations

import io
import os
from datetime import datetime
from pathlib import Path
from typing import Any

import arabic_reshaper
from bidi.algorithm import get_display
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

FONT_DIR = Path(__file__).resolve().parents[2] / "assets" / "fonts"
ARABIC_FONT_FILENAME = os.getenv("PDF_ARABIC_FONT", "Amiri-Regular.ttf")
ARABIC_FONT_NAME = "ArabicBody"
FALLBACK_FONT = "Helvetica"

_ARABIC_REGISTERED: bool | None = None


def _ensure_arabic_font() -> bool:
    """Register the Arabic TTF once; return True if available."""
    global _ARABIC_REGISTERED
    if _ARABIC_REGISTERED is not None:
        return _ARABIC_REGISTERED
    path = FONT_DIR / ARABIC_FONT_FILENAME
    if path.exists():
        try:
            pdfmetrics.registerFont(TTFont(ARABIC_FONT_NAME, str(path)))
            _ARABIC_REGISTERED = True
            return True
        except Exception:
            _ARABIC_REGISTERED = False
            return False
    _ARABIC_REGISTERED = False
    return False


def _shape_ar(text: str) -> str:
    """Apply Arabic reshaping + bidi so ReportLab renders the text correctly."""
    return get_display(arabic_reshaper.reshape(text))


# Static translations for the report. Keep in sync with frontend i18n.
L10N: dict[str, dict[str, str]] = {
    "title":          {"en": "Portfolio Optimization Report", "ar": "تقرير تحسين المحفظة الاستثمارية"},
    "generated_at":   {"en": "Generated at", "ar": "تاريخ الإنشاء"},
    "user":           {"en": "Prepared for", "ar": "أُعدّ لـ"},
    "metrics":        {"en": "Key Metrics", "ar": "المقاييس الرئيسية"},
    "sharpe":         {"en": "Sharpe Ratio", "ar": "نسبة شارب"},
    "expected_return": {"en": "Expected Return (annual)", "ar": "العائد المتوقع (سنوي)"},
    "volatility":     {"en": "Volatility (annual)", "ar": "التذبذب (سنوي)"},
    "risk_free":      {"en": "Risk-free rate", "ar": "المعدل الخالي من المخاطر"},
    "var_95":         {"en": "VaR 95%", "ar": "القيمة المعرضة للخطر (95%)"},
    "weights":        {"en": "Optimal Weights", "ar": "الأوزان المثلى"},
    "ticker":         {"en": "Ticker", "ar": "الرمز"},
    "weight":         {"en": "Weight", "ar": "الوزن"},
    "method":         {"en": "Solver", "ar": "خوارزمية الحل"},
    "disclaimer":     {"en": "Disclaimer", "ar": "إخلاء مسؤولية"},
    "disclaimer_body": {
        "en": "This report is a mathematical simulation based on historical data. It is NOT investment advice.",
        "ar": "هذا التقرير محاكاة رياضية بناءً على بيانات تاريخية ولا يُعدّ توصية استثمارية.",
    },
}


def _t(key: str, locale: str) -> str:
    entry = L10N.get(key, {})
    text = entry.get(locale, entry.get("en", key))
    return _shape_ar(text) if locale == "ar" else text


# ---------------------------------------------------------------------------
def build_run_report(
    *,
    run_id: int,
    user_name: str,
    locale: str,
    run_at: datetime,
    method: str,
    sharpe: float,
    expected_return: float,
    volatility: float,
    risk_free_rate: float,
    var_95: float | None,
    weights: dict[str, float],
    stock_name_map: dict[str, str] | None = None,
) -> bytes:
    """
    Generate a PDF and return its bytes. Bilingual output — when locale is "ar"
    the body text is shaped right-to-left; labels appear in Arabic. When
    locale is "en", Arabic rendering is skipped entirely.
    """
    has_arabic_font = _ensure_arabic_font()
    body_font = ARABIC_FONT_NAME if (locale == "ar" and has_arabic_font) else FALLBACK_FONT

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=1.8 * cm, rightMargin=1.8 * cm,
        topMargin=1.8 * cm, bottomMargin=1.8 * cm,
        title=_t("title", locale),
        author="Tadawul Portfolio Optimizer",
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "TitleAR" if locale == "ar" else "TitleEN",
        parent=styles["Title"],
        fontName=body_font,
        fontSize=20,
        alignment=2 if locale == "ar" else 0,  # 0=left, 2=right
        spaceAfter=14,
    )
    h2_style = ParagraphStyle(
        "H2",
        parent=styles["Heading2"],
        fontName=body_font,
        fontSize=13,
        alignment=2 if locale == "ar" else 0,
        spaceAfter=6,
    )
    body_style = ParagraphStyle(
        "Body",
        parent=styles["BodyText"],
        fontName=body_font,
        fontSize=10,
        alignment=2 if locale == "ar" else 0,
        leading=14,
    )

    story: list[Any] = []
    story.append(Paragraph(_t("title", locale), title_style))
    story.append(
        Paragraph(
            f"{_t('generated_at', locale)}: {run_at.strftime('%Y-%m-%d %H:%M UTC')}",
            body_style,
        )
    )
    story.append(
        Paragraph(
            f"{_t('user', locale)}: {_shape_ar(user_name) if locale == 'ar' else user_name}",
            body_style,
        )
    )
    story.append(Paragraph(f"Run #: {run_id} — {_t('method', locale)}: {method}", body_style))
    story.append(Spacer(1, 10))

    # Metrics table
    story.append(Paragraph(_t("metrics", locale), h2_style))
    metrics_rows = [
        [_t("sharpe", locale), f"{sharpe:.4f}"],
        [_t("expected_return", locale), f"{expected_return * 100:.2f}%"],
        [_t("volatility", locale), f"{volatility * 100:.2f}%"],
        [_t("risk_free", locale), f"{risk_free_rate * 100:.2f}%"],
    ]
    if var_95 is not None:
        metrics_rows.append([_t("var_95", locale), f"{var_95 * 100:.2f}%"])
    metrics_tbl = Table(metrics_rows, colWidths=[7 * cm, 6 * cm])
    metrics_tbl.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), body_font),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f1f5f9")),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story.append(metrics_tbl)
    story.append(Spacer(1, 12))

    # Weights table
    story.append(Paragraph(_t("weights", locale), h2_style))
    header = [_t("ticker", locale), _t("weight", locale)]
    weights_sorted = sorted(weights.items(), key=lambda kv: -kv[1])
    rows = [header]
    for ticker, w in weights_sorted:
        if w < 1e-4:
            continue
        label = ticker
        if stock_name_map and ticker in stock_name_map:
            nm = stock_name_map[ticker]
            label = f"{ticker} — {_shape_ar(nm) if locale == 'ar' else nm}"
        rows.append([label, f"{w * 100:.2f}%"])
    weights_tbl = Table(rows, colWidths=[11 * cm, 4 * cm])
    weights_tbl.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), body_font),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#162849")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("ALIGN", (1, 1), (1, -1), "RIGHT"),
    ]))
    story.append(weights_tbl)
    story.append(Spacer(1, 18))

    # Disclaimer
    story.append(Paragraph(_t("disclaimer", locale), h2_style))
    story.append(Paragraph(_t("disclaimer_body", locale), body_style))

    doc.build(story)
    return buf.getvalue()
