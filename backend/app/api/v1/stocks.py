"""
Stocks / screener endpoints.

Exposes the Tadawul universe with its pre-computed analytics columns so the
frontend can render the screener table locally (only ~234 rows — no need to
paginate or filter server-side).
"""
from __future__ import annotations

import math
from datetime import timedelta
from decimal import Decimal

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import desc, func, select
from sqlalchemy.orm import joinedload

from app.api.deps import CurrentUserDep, DbDep
from app.core.config import settings
from app.db.models import PriceDaily, Sector, SectorIndexDaily, Stock
from app.schemas.stocks import (
    DataSourceRange,
    DataSourcesOut,
    PricePoint,
    ReturnDistributionBucket,
    ReturnPair,
    SectorAveragesOut,
    SectorSummary,
    StockAnalyticsOut,
    StockRow,
)
from app.services.sector_analytics import compute_sector_averages

router = APIRouter(prefix="/stocks", tags=["stocks"])


def _d(v: Decimal | None) -> float | None:
    return float(v) if v is not None else None


@router.get("", response_model=list[StockRow])
def list_stocks(db: DbDep, _: CurrentUserDep) -> list[StockRow]:
    """Return every active stock with its identity, sector, and 14 indicators."""
    rows = db.execute(
        select(Stock)
        .options(joinedload(Stock.sector))
        .where(Stock.is_active.is_(True))
        .order_by(Stock.symbol)
    ).scalars().all()

    return [
        StockRow(
            symbol=s.symbol,
            ticker_suffix=s.ticker_suffix,
            name_ar=s.name_ar,
            name_en=s.name_en,
            industry_ar=s.industry_ar,
            industry_en=s.industry_en,
            sector_code=s.sector.sector_code if s.sector else None,
            # Risk
            beta=_d(s.beta),
            capm_expected_return=_d(s.capm_expected_return),
            daily_volatility=_d(s.daily_volatility),
            annual_volatility=_d(s.annual_volatility),
            sharp_ratio=_d(s.sharp_ratio),
            var_95_daily=_d(s.var_95_daily),
            risk_ranking=s.risk_ranking,
            # Financial
            pe_ratio=_d(s.pe_ratio),
            market_to_book=_d(s.market_to_book),
            roe=_d(s.roe),
            fcf_yield=_d(s.fcf_yield),
            leverage_ratio=_d(s.leverage_ratio),
            eps=_d(s.eps),
            dividend_yield=_d(s.dividend_yield),
            annual_dividend_rate=_d(s.annual_dividend_rate),
            # Price snapshot
            last_price=_d(s.last_price),
            last_price_date=s.last_price_date,
            last_analytics_refresh=s.last_analytics_refresh,
            # Disclosure dates
            last_balance_sheet_date=s.last_balance_sheet_date,
            last_income_statement_date=s.last_income_statement_date,
            latest_dividend_date=s.latest_dividend_date,
        )
        for s in rows
    ]


# ---------------------------------------------------------------------------
# Data sources & update periods footer (Loay slide — مصادر البيانات وفترات التحديث)
# ---------------------------------------------------------------------------
@router.get("/data-sources", response_model=DataSourcesOut)
def data_sources(db: DbDep, _: CurrentUserDep) -> DataSourcesOut:
    """
    Return the three date ranges + provider labels shown in the Screener's
    data-sources footer. Ranges are computed live from the data tables so
    they stay accurate after each refresh.
    """
    px_min, px_max = db.execute(
        select(func.min(PriceDaily.trade_date), func.max(PriceDaily.trade_date))
    ).one()
    sx_min, sx_max = db.execute(
        select(func.min(SectorIndexDaily.trade_date), func.max(SectorIndexDaily.trade_date))
    ).one()
    # "Last update" card shows only the most recent price date.
    return DataSourcesOut(
        stock_prices=DataSourceRange(
            id="stock_prices",
            date_from=px_min, date_to=px_max,
            source_name="Yahoo Finance",
            source_url="https://finance.yahoo.com",
        ),
        sector_indices=DataSourceRange(
            id="sector_indices",
            date_from=sx_min, date_to=sx_max,
            source_name="Mubasher DirectFin",
            source_url="https://www.mubasher.info",
        ),
        last_update=DataSourceRange(
            id="last_update",
            date_from=px_max, date_to=px_max,
            source_name="Yahoo Finance",
            source_url="https://finance.yahoo.com",
        ),
    )


# ---------------------------------------------------------------------------
# Sector averages (Loay slide 83 — "احتساب متوسط أداء القطاع الصناعي")
# ---------------------------------------------------------------------------
@router.get("/sectors-summary", response_model=list[SectorSummary])
def list_sectors_summary(db: DbDep, _: CurrentUserDep) -> list[SectorSummary]:
    """
    Lightweight per-sector summary used to populate the sector picker on the
    Screener: code + bilingual name + count of active stocks.
    """
    rows = db.execute(
        select(
            Sector.sector_code,
            Sector.name_ar,
            Sector.name_en,
            func.count(Stock.id).label("stock_count"),
        )
        .join(Stock, Stock.sector_id == Sector.id, isouter=True)
        .where(Sector.is_active.is_(True))
        .group_by(Sector.id, Sector.sector_code, Sector.name_ar, Sector.name_en)
        .order_by(Sector.sector_code)
    ).all()
    return [
        SectorSummary(
            sector_code=r.sector_code,
            sector_name_ar=r.name_ar,
            sector_name_en=r.name_en,
            stock_count=int(r.stock_count or 0),
        )
        for r in rows
    ]


@router.get("/sector-averages", response_model=SectorAveragesOut)
def sector_averages(
    sector_code: str, db: DbDep, _: CurrentUserDep
) -> SectorAveragesOut:
    """
    Return the average of every analytical indicator across stocks in the
    given sector. Per Loay slide 83: "All analytical indicators for the
    industrial sector are computed on a sector-average basis (sum / count)."

    Risk Ranking is derived from the *averaged* annual_volatility using the
    same slide-105 thresholds applied to individual stocks.
    """
    result = compute_sector_averages(db, sector_code)
    if result is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Unknown sector: {sector_code}")
    return SectorAveragesOut(**result.to_dict())


# ---------------------------------------------------------------------------
# Stock Analyze page (Loay slides 98-99 / 109-111)
# ---------------------------------------------------------------------------
def _resolve_stock(db, ticker: str) -> Stock:
    """Look up a stock by ticker_suffix (preferred) or bare symbol."""
    stock = db.execute(
        select(Stock).options(joinedload(Stock.sector))
        .where(Stock.ticker_suffix == ticker)
    ).scalar_one_or_none()
    if stock is None:
        stock = db.execute(
            select(Stock).options(joinedload(Stock.sector))
            .where(Stock.symbol == ticker)
        ).scalar_one_or_none()
    if stock is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Unknown stock: {ticker}")
    return stock


def _support_resistance(prices: list[float]) -> tuple[float | None, float | None, float | None]:
    """Pivot-based support/resistance from the last N days.

    Pivot = (high + low + close_yesterday) / 3
    Support = 2*pivot - high; Resistance = 2*pivot - low
    """
    if len(prices) < 5:
        return None, None, None
    high = max(prices)
    low = min(prices)
    close = prices[-1]
    pivot = (high + low + close) / 3.0
    support = 2 * pivot - high
    resistance = 2 * pivot - low
    midpoint = (support + resistance) / 2.0
    return float(support), float(resistance), float(midpoint)


def _return_distribution(returns: list[float], buckets: int = 25) -> list[ReturnDistributionBucket]:
    """Bucket daily log-returns into a probability distribution centred on the
    mean ± 3σ. Buckets are equal-width over that range.
    """
    if not returns:
        return []
    mean = sum(returns) / len(returns)
    var = sum((r - mean) ** 2 for r in returns) / max(len(returns) - 1, 1)
    sd = math.sqrt(var) if var > 0 else 0.001
    lower_bound = mean - 3 * sd
    upper_bound = mean + 3 * sd
    width = (upper_bound - lower_bound) / buckets
    counts = [0] * buckets
    for r in returns:
        idx = int((r - lower_bound) / width) if width > 0 else 0
        idx = max(0, min(buckets - 1, idx))
        counts[idx] += 1
    total = float(len(returns))
    return [
        ReturnDistributionBucket(
            lower=round(lower_bound + i * width, 6),
            upper=round(lower_bound + (i + 1) * width, 6),
            frequency_pct=round(100.0 * counts[i] / total, 4),
        )
        for i in range(buckets)
    ]


@router.get("/{ticker}/analytics", response_model=StockAnalyticsOut)
def stock_analytics(ticker: str, db: DbDep, _: CurrentUserDep) -> StockAnalyticsOut:
    """
    Per-stock analysis payload — drives the Stock Analyze page (Loay slides
    98-99 / 109-111). Combines:
      - the 14 core indicators + 16 extended ratios (already on the row);
      - last-30-days price action for support/resistance + the price chart;
      - last-3-years daily returns for the probability-distribution chart;
      - last-6-months stock-vs-index daily-return pair series.
    """
    stock = _resolve_stock(db, ticker)
    sector_code = stock.sector.sector_code if stock.sector else None

    # Price history — last 250 trading days (for 52w / min/max return)
    px_rows = db.execute(
        select(PriceDaily.trade_date, PriceDaily.close)
        .where(PriceDaily.stock_id == stock.id)
        .order_by(desc(PriceDaily.trade_date))
        .limit(250)
    ).all()
    px_rows = list(reversed(px_rows))  # oldest → newest
    closes = [float(r.close) for r in px_rows]
    dates = [r.trade_date for r in px_rows]

    week52_high = max(closes) if closes else None
    week52_low = min(closes) if closes else None
    avg_midpoint = (
        (week52_high + week52_low) / 2.0 if week52_high is not None and week52_low is not None else None
    )

    # Daily log-returns + min/max
    returns: list[float] = []
    for i in range(1, len(closes)):
        prev, cur = closes[i - 1], closes[i]
        if prev > 0 and cur > 0:
            returns.append(math.log(cur / prev))
    min_return = min(returns) if returns else None
    max_return = max(returns) if returns else None

    # Last 30 trading days — for support/resistance + price chart
    last30_closes = closes[-30:]
    last30_dates = dates[-30:]
    support, resistance, midpoint = _support_resistance(last30_closes)
    price_history = [
        PricePoint(trade_date=d, close=c) for d, c in zip(last30_dates, last30_closes)
    ]

    # Probability-distribution buckets across all 250d returns
    distribution = _return_distribution(returns, buckets=25)

    # Stock vs index daily-return pair — last 6 months (~125 trading days)
    pair_dates = dates[-126:]
    pair_closes = closes[-126:]
    stock_returns: list[tuple] = []
    for i in range(1, len(pair_closes)):
        prev, cur = pair_closes[i - 1], pair_closes[i]
        if prev > 0 and cur > 0:
            stock_returns.append((pair_dates[i], math.log(cur / prev)))

    # Map dates → index returns from the stock's sector index
    index_returns_by_date: dict = {}
    if stock.sector_id and stock_returns:
        idx_rows = db.execute(
            select(SectorIndexDaily.trade_date, SectorIndexDaily.close)
            .where(SectorIndexDaily.sector_id == stock.sector_id)
            .where(SectorIndexDaily.trade_date >= stock_returns[0][0] - timedelta(days=2))
            .order_by(SectorIndexDaily.trade_date)
        ).all()
        idx_pairs: list[tuple] = []
        for i in range(1, len(idx_rows)):
            prev = float(idx_rows[i - 1].close)
            cur = float(idx_rows[i].close)
            if prev > 0 and cur > 0:
                idx_pairs.append((idx_rows[i].trade_date, math.log(cur / prev)))
        index_returns_by_date = {d: r for d, r in idx_pairs}

    stock_vs_index = [
        ReturnPair(
            trade_date=d,
            stock_return=round(r, 6),
            index_return=(round(index_returns_by_date[d], 6) if d in index_returns_by_date else None),
        )
        for d, r in stock_returns
    ]

    # CAPM expected returns (uses admin_config risk-free rate; falls back to
    # settings if the row is empty)
    rf = settings.default_risk_free_rate
    beta = float(stock.beta) if stock.beta is not None else 1.0
    market_mu = float(stock.capm_expected_return) if stock.capm_expected_return is not None else rf + 0.05
    expected_annual = float(stock.capm_expected_return) if stock.capm_expected_return is not None else None
    expected_daily = expected_annual / 252.0 if expected_annual is not None else None

    return StockAnalyticsOut(
        symbol=stock.symbol,
        ticker_suffix=stock.ticker_suffix,
        name_ar=stock.name_ar,
        name_en=stock.name_en,
        sector_code=sector_code,
        industry_ar=stock.industry_ar,
        industry_en=stock.industry_en,
        last_price=_d(stock.last_price),
        last_price_date=stock.last_price_date,
        week52_high=week52_high,
        week52_low=week52_low,
        avg_price_midpoint=avg_midpoint,
        min_return_250d=min_return,
        max_return_250d=max_return,
        beta=_d(stock.beta),
        capm_expected_return=_d(stock.capm_expected_return),
        daily_volatility=_d(stock.daily_volatility),
        annual_volatility=_d(stock.annual_volatility),
        sharp_ratio=_d(stock.sharp_ratio),
        var_95_daily=_d(stock.var_95_daily),
        risk_ranking=stock.risk_ranking,
        pe_ratio=_d(stock.pe_ratio),
        market_to_book=_d(stock.market_to_book),
        roe=_d(stock.roe),
        fcf_yield=_d(stock.fcf_yield),
        leverage_ratio=_d(stock.leverage_ratio),
        eps=_d(stock.eps),
        dividend_yield=_d(stock.dividend_yield),
        annual_dividend_rate=_d(stock.annual_dividend_rate),
        current_ratio=_d(stock.current_ratio),
        quick_ratio=_d(stock.quick_ratio),
        cash_ratio=_d(stock.cash_ratio),
        interest_coverage_ratio=_d(stock.interest_coverage_ratio),
        asset_turnover=_d(stock.asset_turnover),
        inventory_turnover=_d(stock.inventory_turnover),
        receivables_turnover=_d(stock.receivables_turnover),
        payables_turnover=_d(stock.payables_turnover),
        roa=_d(stock.roa),
        net_profit_margin=_d(stock.net_profit_margin),
        gross_profit_margin=_d(stock.gross_profit_margin),
        book_value_per_share=_d(stock.book_value_per_share),
        revenue_per_share=_d(stock.revenue_per_share),
        debt_to_market_cap=_d(stock.debt_to_market_cap),
        cash_to_assets=_d(stock.cash_to_assets),
        receivables_to_assets=_d(stock.receivables_to_assets),
        last_balance_sheet_date=stock.last_balance_sheet_date,
        last_income_statement_date=stock.last_income_statement_date,
        latest_dividend_date=stock.latest_dividend_date,
        support_price=support,
        resistance_price=resistance,
        midpoint_price=midpoint,
        return_distribution=distribution,
        price_history=price_history,
        stock_vs_index=stock_vs_index,
        expected_annual_return=expected_annual,
        expected_daily_return=expected_daily,
    )
