"""
Sector-level averages — Loay's slide ("احتساب متوسط أداء القطاع الصناعي").

For a given sector code, average each of the 14 analytical indicators across
all stocks in that sector. Risk Ranking is then derived from the *averaged*
annual volatility per the same PPTX-slide-105 thresholds used for individual
stocks.

Nulls are treated as "no data" and excluded from each indicator's average
(rather than dragging the mean to 0). If every stock is null on a field, the
average is null and the frontend renders "—".
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Sector, Stock
from app.services.stock_analytics import compute_risk_ranking


@dataclass
class SectorAverages:
    sector_code: str
    sector_name_ar: str
    sector_name_en: str
    stock_count: int
    # Risk indicators (6)
    avg_beta: float | None
    avg_capm_expected_return: float | None
    avg_daily_volatility: float | None
    avg_annual_volatility: float | None
    avg_sharp_ratio: float | None
    avg_var_95_daily: float | None
    risk_ranking: str | None
    # Financial indicators (8)
    avg_pe_ratio: float | None
    avg_market_to_book: float | None
    avg_roe: float | None
    avg_fcf_yield: float | None
    avg_leverage_ratio: float | None
    avg_eps: float | None
    avg_dividend_yield: float | None
    avg_annual_dividend_rate: float | None

    def to_dict(self) -> dict:
        return asdict(self)


# Map model attribute → SectorAverages key
_FIELDS: list[tuple[str, str]] = [
    ("beta",                    "avg_beta"),
    ("capm_expected_return",    "avg_capm_expected_return"),
    ("daily_volatility",        "avg_daily_volatility"),
    ("annual_volatility",       "avg_annual_volatility"),
    ("sharp_ratio",             "avg_sharp_ratio"),
    ("var_95_daily",            "avg_var_95_daily"),
    ("pe_ratio",                "avg_pe_ratio"),
    ("market_to_book",          "avg_market_to_book"),
    ("roe",                     "avg_roe"),
    ("fcf_yield",               "avg_fcf_yield"),
    ("leverage_ratio",          "avg_leverage_ratio"),
    ("eps",                     "avg_eps"),
    ("dividend_yield",          "avg_dividend_yield"),
    ("annual_dividend_rate",    "avg_annual_dividend_rate"),
]


def compute_sector_averages(db: Session, sector_code: str) -> SectorAverages | None:
    """
    Compute the average of every analytical indicator across all active stocks
    in the given sector. Returns `None` when the sector code is unknown.
    """
    sector = db.execute(
        select(Sector).where(Sector.sector_code == sector_code)
    ).scalar_one_or_none()
    if sector is None:
        return None

    stocks = db.execute(
        select(Stock).where(
            Stock.sector_id == sector.id,
            Stock.is_active.is_(True),
        )
    ).scalars().all()

    averages: dict[str, float | None] = {}
    for attr, key in _FIELDS:
        values: list[float] = []
        for s in stocks:
            v = getattr(s, attr)
            if v is None:
                continue
            try:
                values.append(float(v))
            except (TypeError, ValueError):
                continue
        averages[key] = round(sum(values) / len(values), 6) if values else None

    avg_annual_vol = averages.get("avg_annual_volatility")
    risk_ranking = compute_risk_ranking(Decimal(str(avg_annual_vol))) if avg_annual_vol is not None else None

    return SectorAverages(
        sector_code=sector.sector_code,
        sector_name_ar=sector.name_ar,
        sector_name_en=sector.name_en,
        stock_count=len(stocks),
        risk_ranking=risk_ranking,
        **averages,  # type: ignore[arg-type]
    )
