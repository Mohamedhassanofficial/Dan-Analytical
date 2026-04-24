"""
Yahoo Finance price refresher for the Tadawul universe.

Responsibilities:
    - Pull incremental daily OHLCV for each active stock (last known date → today).
    - Upsert into `prices_daily`, skipping duplicates via (stock_id, trade_date).
    - Record a per-stock summary (rows added, errors) to `audit_log`.
    - Be resilient to rate-limiting (yfinance occasionally returns empty frames
      — we retry up to `settings.yfinance_max_retries` with exponential backoff).

Run locally (from backend/):
    python -m scripts.refresh_prices

Schedule in production via APScheduler (wired in `app/main.py`) or cron:
    0 20 * * * cd /app/backend && python -m scripts.refresh_prices
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

import pandas as pd
import yfinance as yf
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import AuditLog, PriceDaily, Stock

log = logging.getLogger(__name__)

# Tadawul trades Sunday-Thursday. yfinance returns an empty frame on closed
# days — that's fine; we just skip them.
HISTORY_GRACE_DAYS = 3


@dataclass
class StockRefreshResult:
    symbol: str
    ticker: str
    rows_added: int = 0
    last_date: date | None = None
    error: str | None = None


@dataclass
class RefreshSummary:
    started_at: date
    stocks_processed: int = 0
    total_rows_added: int = 0
    failures: int = 0
    per_stock: list[StockRefreshResult] = field(default_factory=list)


# ----------------------------------------------------------------------------
def _last_price_date(db: Session, stock_id: int) -> date | None:
    return db.execute(
        select(func.max(PriceDaily.trade_date)).where(PriceDaily.stock_id == stock_id)
    ).scalar_one_or_none()


def _safe_decimal(v: object) -> Decimal | None:
    """yfinance returns floats with NaN for holidays. Convert safely."""
    if v is None or (isinstance(v, float) and (v != v)):  # NaN check
        return None
    try:
        return Decimal(str(v))
    except (InvalidOperation, TypeError):
        return None


def _fetch_history(
    ticker: str, start: date, end: date, retries: int, timeout: int
) -> pd.DataFrame:
    """Call yfinance with retry + backoff. Returns empty DataFrame on final failure."""
    last_exc: Exception | None = None
    for attempt in range(retries):
        try:
            df = yf.download(
                ticker,
                start=start.isoformat(),
                end=(end + timedelta(days=1)).isoformat(),
                progress=False,
                auto_adjust=False,
                timeout=timeout,
                threads=False,
            )
            if df is not None and not df.empty:
                return df
            # Empty frame on a closed day is legitimate — don't retry
            if (end - start).days <= HISTORY_GRACE_DAYS:
                return pd.DataFrame()
        except Exception as exc:  # yfinance can throw JSONDecodeError etc.
            last_exc = exc
        time.sleep(2 ** attempt)

    if last_exc is not None:
        log.warning("yfinance fetch failed for %s: %s", ticker, last_exc)
    return pd.DataFrame()


# ----------------------------------------------------------------------------
def refresh_stock(db: Session, stock: Stock, today: date) -> StockRefreshResult:
    """
    Pull missing prices for a single stock and upsert them. Returns a
    per-stock summary suitable for logging to audit_log.
    """
    result = StockRefreshResult(symbol=stock.symbol, ticker=stock.ticker_suffix)

    last = _last_price_date(db, stock.id)
    # Default backfill: ~5 years. In production this is superseded by the
    # seed-history workflow that loads the full 10-year CSV.
    start = (last + timedelta(days=1)) if last else (today - timedelta(days=365 * 5))
    if start > today:
        result.last_date = last
        return result  # already up-to-date

    df = _fetch_history(
        ticker=stock.ticker_suffix,
        start=start,
        end=today,
        retries=settings.yfinance_max_retries,
        timeout=settings.yfinance_request_timeout_sec,
    )
    if df.empty:
        return result

    # yfinance returns MultiIndex columns when a single ticker is passed as a list;
    # normalize to flat column names.
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    rows: list[dict] = []
    for ts, row in df.iterrows():
        trade_date = ts.date() if hasattr(ts, "date") else ts
        rows.append(
            {
                "stock_id": stock.id,
                "trade_date": trade_date,
                "open": _safe_decimal(row.get("Open")),
                "high": _safe_decimal(row.get("High")),
                "low": _safe_decimal(row.get("Low")),
                "close": _safe_decimal(row.get("Close")),
                "adj_close": _safe_decimal(row.get("Adj Close")),
                "volume": int(row["Volume"]) if not pd.isna(row.get("Volume")) else None,
            }
        )

    if not rows:
        return result

    stmt = pg_insert(PriceDaily).values(rows).on_conflict_do_nothing(
        index_elements=["stock_id", "trade_date"]
    )
    db.execute(stmt)
    result.rows_added = len(rows)
    result.last_date = max(r["trade_date"] for r in rows)
    return result


# ----------------------------------------------------------------------------
def refresh_all(db: Session, today: date | None = None) -> RefreshSummary:
    """
    Refresh every active stock. Commits after each stock so that a later
    failure doesn't roll back earlier successes.
    """
    today = today or date.today()
    summary = RefreshSummary(started_at=today)

    active_stocks = db.execute(
        select(Stock).where(Stock.is_active.is_(True)).order_by(Stock.symbol)
    ).scalars().all()

    for stock in active_stocks:
        try:
            per = refresh_stock(db, stock, today)
            db.commit()
        except Exception as exc:
            db.rollback()
            per = StockRefreshResult(
                symbol=stock.symbol,
                ticker=stock.ticker_suffix,
                error=str(exc)[:500],
            )
            summary.failures += 1

        summary.per_stock.append(per)
        summary.stocks_processed += 1
        summary.total_rows_added += per.rows_added

    # Audit-log the run (required by PDF §3 — Audit Logging)
    db.add(
        AuditLog(
            user_id=None,
            action="market_data.refresh",
            resource_type="stocks",
            resource_id=None,
            details={
                "started_at": summary.started_at.isoformat(),
                "stocks_processed": summary.stocks_processed,
                "total_rows_added": summary.total_rows_added,
                "failures": summary.failures,
            },
        )
    )
    db.commit()
    return summary
