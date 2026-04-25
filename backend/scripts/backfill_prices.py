"""
Bulk historical price backfill for the 234-stock Tadawul universe.

Unlike `refresh_prices.py` (which does incremental daily updates), this
script downloads the full lookback window (~5 years) for every active stock.
It is designed to be:

  - **Resumable**: skips stocks that already have enough history
  - **Rate-limit safe**: configurable sleep between stocks
  - **Batched**: processes N stocks, then commits, so progress is never lost
  - **Verbose**: real-time progress with ETA

Usage (from backend/):
    python -m scripts.backfill_prices                    # default 5-year window
    python -m scripts.backfill_prices --years 10         # 10-year backfill
    python -m scripts.backfill_prices --batch 20         # 20 stocks per batch
    python -m scripts.backfill_prices --sleep 1.0        # 1s between stocks
    python -m scripts.backfill_prices --symbols 2222.SR,1120.SR  # specific stocks
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import date, timedelta
from pathlib import Path

from sqlalchemy import func, select

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.models import PriceDaily, Stock  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.services.market_data import refresh_stock  # noqa: E402

log = logging.getLogger(__name__)


def backfill(
    years: int = 5,
    batch_size: int = 10,
    sleep_sec: float = 0.5,
    symbols: list[str] | None = None,
    min_days: int = 100,
) -> dict:
    """
    Download historical prices for all active stocks.

    Parameters
    ----------
    years      : how many years of history to target
    batch_size : commit after this many stocks
    sleep_sec  : pause between individual yfinance calls
    symbols    : if set, only backfill these specific tickers
    min_days   : skip stocks already having ≥ this many price rows

    Returns
    -------
    Summary dict with stats.
    """
    today = date.today()
    target_start = today - timedelta(days=int(years * 365.25))

    with SessionLocal() as db:
        query = select(Stock).where(Stock.is_active.is_(True)).order_by(Stock.symbol)
        if symbols:
            query = query.where(Stock.ticker_suffix.in_(symbols))
        stocks = db.execute(query).scalars().all()

    total = len(stocks)
    print(f"\n📥 Backfill: {total} stocks, {years}-year window")
    print(f"   Target start: {target_start}, batch size: {batch_size}, sleep: {sleep_sec}s")
    print(f"   Skip threshold: ≥{min_days} existing price rows\n")

    stats = {
        "total_stocks": total,
        "skipped": 0,
        "processed": 0,
        "rows_added": 0,
        "failures": 0,
        "failed_tickers": [],
    }

    start_time = time.time()

    for i, stock in enumerate(stocks, 1):
        # Check existing row count
        with SessionLocal() as db:
            existing = db.execute(
                select(func.count())
                .where(PriceDaily.stock_id == stock.id)
            ).scalar() or 0

        if existing >= min_days:
            stats["skipped"] += 1
            _print_progress(i, total, stock.ticker_suffix, "SKIP", existing, start_time)
            continue

        # Download
        try:
            with SessionLocal() as db:
                # Re-fetch the stock in this session
                s = db.get(Stock, stock.id)
                result = refresh_stock(db, s, today)
                db.commit()

            stats["processed"] += 1
            stats["rows_added"] += result.rows_added
            _print_progress(i, total, stock.ticker_suffix, "OK", result.rows_added, start_time)

        except Exception as exc:
            stats["failures"] += 1
            stats["failed_tickers"].append(stock.ticker_suffix)
            _print_progress(i, total, stock.ticker_suffix, f"FAIL: {exc}", 0, start_time)

        # Rate limit
        if sleep_sec > 0:
            time.sleep(sleep_sec)

    elapsed = time.time() - start_time

    print(f"\n{'=' * 60}")
    print(f"✅ Backfill complete in {elapsed:.0f}s ({elapsed / 60:.1f} min)")
    print(f"   Processed:  {stats['processed']}")
    print(f"   Skipped:    {stats['skipped']} (already have ≥{min_days} rows)")
    print(f"   Rows added: {stats['rows_added']:,}")
    print(f"   Failures:   {stats['failures']}")
    if stats["failed_tickers"]:
        print(f"   Failed:     {', '.join(stats['failed_tickers'][:20])}")
    print(f"{'=' * 60}\n")

    return stats


def _print_progress(i: int, total: int, ticker: str, status: str, detail: int, start_time: float):
    elapsed = time.time() - start_time
    rate = i / elapsed if elapsed > 0 else 0
    eta = (total - i) / rate if rate > 0 else 0
    pct = i / total * 100
    print(
        f"   [{i:>3}/{total}] {pct:5.1f}% | {ticker:<10s} | {status:<20s} "
        f"| +{detail:>5} rows | ETA {eta:.0f}s"
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="Bulk backfill Tadawul price history from yfinance.")
    ap.add_argument("--years", type=int, default=5, help="Years of history (default 5)")
    ap.add_argument("--batch", type=int, default=10, help="Stocks per commit batch (default 10)")
    ap.add_argument("--sleep", type=float, default=0.5, help="Seconds between yfinance calls (default 0.5)")
    ap.add_argument("--symbols", type=str, default=None, help="Comma-separated tickers (default: all active)")
    ap.add_argument("--min-days", type=int, default=100, help="Skip stocks with this many existing rows (default 100)")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(asctime)s %(levelname)-5s %(name)s — %(message)s",
    )

    symbols = None
    if args.symbols:
        symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]

    backfill(
        years=args.years,
        batch_size=args.batch,
        sleep_sec=args.sleep,
        symbols=symbols,
        min_days=args.min_days,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
