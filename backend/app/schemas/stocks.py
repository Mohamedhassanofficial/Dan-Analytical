"""Pydantic schemas for the stocks / screener API."""
from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel


class StockRow(BaseModel):
    """
    One row of the Screener table. Every numeric field is decimal / annual
    so the frontend renders them consistently. `null` means the indicator
    has not been computed yet — either a fresh stock or a yfinance coverage
    gap. The Screener renders NULL as "—" per the accountant coloring rule.
    """
    # Identity
    symbol: str
    ticker_suffix: str
    name_ar: str | None
    name_en: str | None
    industry_ar: str | None
    industry_en: str | None
    sector_code: str | None

    # Risk indicators (group 1 of 2 in the Screener filter UI)
    beta: float | None
    capm_expected_return: float | None
    daily_volatility: float | None
    annual_volatility: float | None
    sharp_ratio: float | None
    var_95_daily: float | None
    risk_ranking: str | None

    # Financial indicators (group 2)
    pe_ratio: float | None
    market_to_book: float | None
    roe: float | None
    fcf_yield: float | None
    leverage_ratio: float | None
    eps: float | None
    dividend_yield: float | None
    annual_dividend_rate: float | None

    # Price snapshot
    last_price: float | None
    last_price_date: date | None
    last_analytics_refresh: datetime | None

    model_config = {"from_attributes": True}
