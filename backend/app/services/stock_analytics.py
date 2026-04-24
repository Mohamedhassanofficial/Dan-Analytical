"""
Per-stock analytics refresh — populates the 14 indicator columns on `stocks`.

For each stock we:
  1. Call yfinance `Ticker(symbol).info` for fundamentals
     (P/E, EPS, dividend yield, ROE, leverage, etc.).
  2. Load the last N trading days of prices from `prices_daily` and compute
     returns-based metrics (daily vol, annual vol, Sharpe, β vs TASI, VaR 95%).
  3. Compute categorical Risk Ranking from annual volatility per PPTX slide 105.
  4. UPDATE the stock row with everything non-None.

yfinance coverage for Tadawul (.SR) is patchy — any fundamental can come back
`None` or `NaN`. We write what we have and leave gaps as NULL. The frontend
renders NULL as "—" per the accountant coloring rule.

The orchestrator throttles calls (default 0.3 s / ticker) and retries on
`JSONDecodeError`. A single `AuditLog` row is written per run summarizing
how many stocks were touched and how many fundamentals populated.
"""
from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

import numpy as np
import yfinance as yf
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import AuditLog, PriceDaily, Sector, SectorIndexDaily, Stock

log = logging.getLogger(__name__)

TASI_CODE = "TASI"


# ----------------------------------------------------------------------------
@dataclass
class StockAnalyticsResult:
    symbol: str
    ticker: str
    updated_fields: list[str] = field(default_factory=list)
    error: str | None = None


@dataclass
class AnalyticsRefreshSummary:
    started_at: datetime
    stocks_processed: int = 0
    stocks_updated: int = 0
    fundamentals_populated: int = 0
    failures: int = 0
    per_stock: list[StockAnalyticsResult] = field(default_factory=list)


# ----------------------------------------------------------------------------
# Risk Ranking — PPTX slide 105 formula
# ----------------------------------------------------------------------------
RANKING_CONSERVATIVE = "Conservative"
RANKING_MODERATE = "Moderately Conservative"
RANKING_AGGRESSIVE = "Aggressive"
RANKING_VERY_AGGRESSIVE = "Very Aggressive"

# Risk Ranking labels are admin-editable via ui_labels on the frontend, but the
# DB value is one of these four enum strings for deterministic filtering.


def compute_risk_ranking(annual_vol: Decimal | float | None) -> str | None:
    """
    PPTX slide 105:
      ≤ 10% → Conservative
      ≤ 20% → Moderately Conservative
      ≤ 30% → Aggressive
      else  → Very Aggressive
    """
    if annual_vol is None:
        return None
    v = float(annual_vol)
    if math.isnan(v) or v < 0:
        return None
    if v <= 0.10:
        return RANKING_CONSERVATIVE
    if v <= 0.20:
        return RANKING_MODERATE
    if v <= 0.30:
        return RANKING_AGGRESSIVE
    return RANKING_VERY_AGGRESSIVE


# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------
def _safe_decimal(v: Any, *, places: int = 6) -> Decimal | None:
    """Convert a potentially messy yfinance value to Decimal or None.

    Returns None for NaN, None, empty, non-numeric, inf.
    """
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if math.isnan(f) or math.isinf(f):
        return None
    try:
        return Decimal(str(round(f, places)))
    except (InvalidOperation, TypeError):
        return None


def _fetch_info_with_retry(ticker: str, retries: int = 3, timeout: int = 20) -> dict:
    """yfinance.Ticker().info with retry/backoff. Returns {} on persistent failure."""
    last_exc: Exception | None = None
    for attempt in range(retries):
        try:
            t = yf.Ticker(ticker)
            info = t.info or {}
            if info and "regularMarketPreviousClose" in info:
                return info
            if info:
                return info
        except Exception as exc:  # noqa: BLE001 — yfinance throws many types
            last_exc = exc
        time.sleep(2 ** attempt)
    if last_exc:
        log.warning("yfinance.info failed for %s: %s", ticker, last_exc)
    return {}


def _load_returns_and_market(
    db: Session,
    stock_id: int,
    end: date,
    lookback_days: int,
) -> tuple[np.ndarray | None, np.ndarray | None]:
    """
    Return (stock_daily_log_returns, market_daily_log_returns) aligned on
    common trading days, or (None, None) if either side is missing.
    """
    # Widen the calendar window by ~40 % to account for weekends / holidays.
    start = end - timedelta(days=int(lookback_days * 7 / 5) + 30)

    stock_rows = db.execute(
        select(PriceDaily.trade_date, PriceDaily.adj_close, PriceDaily.close)
        .where(
            PriceDaily.stock_id == stock_id,
            PriceDaily.trade_date >= start,
            PriceDaily.trade_date <= end,
        )
        .order_by(PriceDaily.trade_date)
    ).all()
    if len(stock_rows) < 30:
        return None, None

    tasi = db.execute(
        select(Sector).where(Sector.sector_code == TASI_CODE)
    ).scalar_one_or_none()
    if tasi is None:
        return None, None

    market_rows = db.execute(
        select(SectorIndexDaily.trade_date, SectorIndexDaily.close)
        .where(
            SectorIndexDaily.sector_id == tasi.id,
            SectorIndexDaily.trade_date >= start,
            SectorIndexDaily.trade_date <= end,
        )
        .order_by(SectorIndexDaily.trade_date)
    ).all()
    if len(market_rows) < 30:
        return None, None

    # Align on the intersection of trading days that both sides have.
    stock_map = {
        r.trade_date: float(r.adj_close if r.adj_close is not None else r.close)
        for r in stock_rows
    }
    market_map = {r.trade_date: float(r.close) for r in market_rows}
    common = sorted(set(stock_map) & set(market_map))
    common = common[-lookback_days:]
    if len(common) < 30:
        return None, None

    stock_prices = np.array([stock_map[d] for d in common], dtype=float)
    market_prices = np.array([market_map[d] for d in common], dtype=float)

    # Log returns
    stock_ret = np.log(stock_prices[1:] / stock_prices[:-1])
    market_ret = np.log(market_prices[1:] / market_prices[:-1])
    return stock_ret, market_ret


# ----------------------------------------------------------------------------
# Main per-stock refresh
# ----------------------------------------------------------------------------
def refresh_stock_analytics(
    db: Session,
    stock: Stock,
    risk_free_rate: float,
    trading_days_per_year: int,
    lookback_days: int,
    end: date,
) -> StockAnalyticsResult:
    """
    Populate the 14 indicator columns on a single `Stock` row.

    Any field that cannot be computed (missing yfinance data, insufficient
    price history) is left as NULL. The row is committed only if at least
    one field changed.
    """
    result = StockAnalyticsResult(symbol=stock.symbol, ticker=stock.ticker_suffix)

    # ---- Fundamentals via yfinance.info -----------------------------------
    info = _fetch_info_with_retry(stock.ticker_suffix)

    pe = _safe_decimal(info.get("trailingPE"), places=4)
    mb = _safe_decimal(info.get("priceToBook"), places=4)
    roe = _safe_decimal(info.get("returnOnEquity"), places=6)
    eps = _safe_decimal(info.get("trailingEps"), places=4)
    div_yield = _safe_decimal(info.get("trailingAnnualDividendYield"), places=6)
    div_rate = _safe_decimal(info.get("trailingAnnualDividendRate"), places=4)
    last_price = _safe_decimal(info.get("regularMarketPreviousClose"), places=4)

    # FCF Yield = freeCashflow / (sharesOutstanding × price)
    fcf_yield: Decimal | None = None
    try:
        fcf = info.get("freeCashflow")
        shares = info.get("sharesOutstanding")
        px = info.get("regularMarketPreviousClose")
        if fcf and shares and px and shares > 0 and px > 0:
            fcf_yield = _safe_decimal(float(fcf) / (float(shares) * float(px)), places=6)
    except (TypeError, ValueError, ZeroDivisionError):
        fcf_yield = None

    # Leverage = totalDebt / (totalDebt + marketCap)  — a debt/enterprise-value proxy.
    # The PPTX slide 106 example uses `totalDebt / totalEquity`, but yfinance
    # exposes `debtToEquity` directly (as a %), which is the same thing.
    leverage: Decimal | None = None
    dte = info.get("debtToEquity")
    if dte is not None:
        leverage = _safe_decimal(float(dte) / 100.0, places=6)  # yfinance returns % → decimal

    # ---- Returns-based metrics from PriceDaily ----------------------------
    daily_vol: Decimal | None = None
    annual_vol: Decimal | None = None
    beta: Decimal | None = None
    sharp: Decimal | None = None
    var_1d: Decimal | None = None

    stock_ret, market_ret = _load_returns_and_market(
        db, stock.id, end, lookback_days
    )
    if stock_ret is not None and market_ret is not None and stock_ret.size >= 30:
        d_vol = float(np.std(stock_ret, ddof=0))
        a_vol = d_vol * math.sqrt(trading_days_per_year)
        mean_daily = float(np.mean(stock_ret))
        mean_annual = mean_daily * trading_days_per_year

        daily_vol = _safe_decimal(d_vol)
        annual_vol = _safe_decimal(a_vol)

        if a_vol > 1e-9:
            sharp = _safe_decimal((mean_annual - risk_free_rate) / a_vol)

        mkt_var = float(np.var(market_ret, ddof=0))
        if mkt_var > 1e-16:
            cov = float(np.cov(stock_ret, market_ret, ddof=0)[0, 1])
            beta = _safe_decimal(cov / mkt_var)

        # Parametric VaR 95% 1-day: -(μ - z·σ); z ≈ 1.645 for 95%.
        z = 1.6448536269514722
        var_value = max(0.0, -(mean_daily - z * d_vol))
        var_1d = _safe_decimal(var_value)

    # Risk Ranking from annual vol
    ranking = compute_risk_ranking(annual_vol)

    # ---- Write back -------------------------------------------------------
    updates: dict[str, Any] = {
        "pe_ratio": pe,
        "market_to_book": mb,
        "roe": roe,
        "eps": eps,
        "dividend_yield": div_yield,
        "annual_dividend_rate": div_rate,
        "fcf_yield": fcf_yield,
        "leverage_ratio": leverage,
        "last_price": last_price,
        "daily_volatility": daily_vol,
        "annual_volatility": annual_vol,
        "beta": beta,
        "sharp_ratio": sharp,
        "var_95_daily": var_1d,
        "risk_ranking": ranking,
    }

    now = datetime.now(timezone.utc)
    changed = False
    for field_name, value in updates.items():
        if value is not None and getattr(stock, field_name) != value:
            setattr(stock, field_name, value)
            result.updated_fields.append(field_name)
            changed = True

    # Always record that we tried, even if nothing changed.
    stock.last_analytics_refresh = now
    if end is not None and last_price is not None:
        stock.last_price_date = end
    if changed:
        result.updated_fields.append("last_analytics_refresh")

    return result


# ----------------------------------------------------------------------------
# Orchestrator
# ----------------------------------------------------------------------------
def refresh_all(
    db: Session,
    risk_free_rate: float | None = None,
    sleep_sec: float = 0.3,
    symbols: list[str] | None = None,
    as_of: date | None = None,
) -> AnalyticsRefreshSummary:
    """
    Refresh analytics for every active stock (or just `symbols` if given).

    Commits after each stock so a later failure doesn't roll back earlier
    successes. A single `AuditLog` row is written at the end summarising the
    run (required by PDF §3 Audit Logging).
    """
    if risk_free_rate is None:
        risk_free_rate = settings.default_risk_free_rate
    end = as_of or date.today()
    # Use the most recent trading date we actually have prices for
    most_recent = db.execute(select(func.max(PriceDaily.trade_date))).scalar()
    if most_recent:
        end = min(end, most_recent)

    lookback = settings.default_lookback_days
    tdy = settings.trading_days_per_year

    summary = AnalyticsRefreshSummary(started_at=datetime.now(timezone.utc))

    q = select(Stock).where(Stock.is_active.is_(True)).order_by(Stock.symbol)
    if symbols:
        q = q.where(Stock.ticker_suffix.in_(symbols))
    stocks = db.execute(q).scalars().all()

    for stock in stocks:
        try:
            per = refresh_stock_analytics(
                db, stock,
                risk_free_rate=risk_free_rate,
                trading_days_per_year=tdy,
                lookback_days=lookback,
                end=end,
            )
            db.commit()
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            per = StockAnalyticsResult(
                symbol=stock.symbol,
                ticker=stock.ticker_suffix,
                error=str(exc)[:500],
            )
            summary.failures += 1

        summary.per_stock.append(per)
        summary.stocks_processed += 1
        if per.updated_fields:
            summary.stocks_updated += 1
            summary.fundamentals_populated += len(per.updated_fields)

        if sleep_sec > 0:
            time.sleep(sleep_sec)

    # Audit log the run (PDF §3)
    db.add(
        AuditLog(
            user_id=None,
            action="analytics.refresh",
            resource_type="stocks",
            resource_id=None,
            details={
                "started_at": summary.started_at.isoformat(),
                "stocks_processed": summary.stocks_processed,
                "stocks_updated": summary.stocks_updated,
                "fundamentals_populated": summary.fundamentals_populated,
                "failures": summary.failures,
                "scope": symbols or "all_active",
                "as_of": end.isoformat(),
            },
        )
    )
    db.commit()
    return summary
