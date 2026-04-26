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

    # Fundamental disclosure dates (rendered in the Screener's Financial
    # Ratios band). None → "—" on the frontend.
    last_balance_sheet_date: date | None
    last_income_statement_date: date | None
    latest_dividend_date: date | None

    model_config = {"from_attributes": True}


class DataSourceRange(BaseModel):
    """Date range + provider info for one data-sources footer card."""
    id: str
    date_from: date | None
    date_to: date | None
    source_name: str
    source_url: str | None


class DataSourcesOut(BaseModel):
    """Payload for the Screener's "مصادر البيانات وفترات التحديث" footer."""
    stock_prices: DataSourceRange
    sector_indices: DataSourceRange
    last_update: DataSourceRange


# ── Stock Analyze page (Loay slides 98-99 / 109-111) ────────────────────────
class ReturnDistributionBucket(BaseModel):
    """One histogram bucket on the stock-return probability chart."""
    lower: float
    upper: float
    frequency_pct: float


class PricePoint(BaseModel):
    trade_date: date
    close: float


class ReturnPair(BaseModel):
    trade_date: date
    stock_return: float
    index_return: float | None


class StockAnalyticsOut(BaseModel):
    """Full payload for the per-stock Analyze page."""
    # Identity
    symbol: str
    ticker_suffix: str
    name_ar: str | None
    name_en: str | None
    sector_code: str | None
    industry_ar: str | None
    industry_en: str | None

    # Stock Movement block
    last_price: float | None
    last_price_date: date | None
    week52_high: float | None
    week52_low: float | None
    avg_price_midpoint: float | None
    min_return_250d: float | None
    max_return_250d: float | None

    # Stock Risk Measurement block
    beta: float | None
    capm_expected_return: float | None
    daily_volatility: float | None
    annual_volatility: float | None
    sharp_ratio: float | None
    var_95_daily: float | None
    risk_ranking: str | None

    # Financial Ratios block — the 14 + the 16 extras from Phase B
    pe_ratio: float | None
    market_to_book: float | None
    roe: float | None
    fcf_yield: float | None
    leverage_ratio: float | None
    eps: float | None
    dividend_yield: float | None
    annual_dividend_rate: float | None
    current_ratio: float | None
    quick_ratio: float | None
    cash_ratio: float | None
    interest_coverage_ratio: float | None
    asset_turnover: float | None
    inventory_turnover: float | None
    receivables_turnover: float | None
    payables_turnover: float | None
    roa: float | None
    net_profit_margin: float | None
    gross_profit_margin: float | None
    book_value_per_share: float | None
    revenue_per_share: float | None
    debt_to_market_cap: float | None
    cash_to_assets: float | None
    receivables_to_assets: float | None

    # Disclosure dates
    last_balance_sheet_date: date | None
    last_income_statement_date: date | None
    latest_dividend_date: date | None

    # Support & resistance (from last 30 trading days)
    support_price: float | None
    resistance_price: float | None
    midpoint_price: float | None

    # Charts: probability distribution + price history + stock-vs-index pair
    return_distribution: list[ReturnDistributionBucket]
    price_history: list[PricePoint]
    stock_vs_index: list[ReturnPair]

    # CAPM-derived expected returns (used by the Expected Stock Return block)
    expected_annual_return: float | None
    expected_daily_return: float | None


class SectorAveragesOut(BaseModel):
    """Sector-level averages of the 14 indicators (Loay's slide 83)."""
    sector_code: str
    sector_name_ar: str
    sector_name_en: str
    stock_count: int
    # Risk
    avg_beta: float | None
    avg_capm_expected_return: float | None
    avg_daily_volatility: float | None
    avg_annual_volatility: float | None
    avg_sharp_ratio: float | None
    avg_var_95_daily: float | None
    risk_ranking: str | None
    # Financial
    avg_pe_ratio: float | None
    avg_market_to_book: float | None
    avg_roe: float | None
    avg_fcf_yield: float | None
    avg_leverage_ratio: float | None
    avg_eps: float | None
    avg_dividend_yield: float | None
    avg_annual_dividend_rate: float | None


class SectorSummary(BaseModel):
    """Lightweight: code + name + stock count, populates the sector picker."""
    sector_code: str
    sector_name_ar: str
    sector_name_en: str
    stock_count: int
