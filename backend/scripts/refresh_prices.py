"""
CLI entry point for the yfinance daily refresh.

Usage (from backend/):
    python -m scripts.refresh_prices
    python -m scripts.refresh_prices --as-of 2026-04-24
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.session import SessionLocal  # noqa: E402
from app.services.market_data import refresh_all  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="Refresh daily Tadawul prices from yfinance.")
    ap.add_argument(
        "--as-of",
        type=date.fromisoformat,
        default=date.today(),
        help="Treat this date as 'today' (useful for backfill testing).",
    )
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-5s %(name)s — %(message)s",
    )

    with SessionLocal() as db:
        summary = refresh_all(db, today=args.as_of)

    print("\n" + "=" * 60)
    print(f"Stocks processed: {summary.stocks_processed}")
    print(f"Rows added:       {summary.total_rows_added:,}")
    print(f"Failures:         {summary.failures}")
    if summary.failures:
        print("\nFirst 10 failures:")
        for r in [x for x in summary.per_stock if x.error][:10]:
            print(f"  {r.symbol} ({r.ticker}): {r.error}")
    return 0 if summary.failures == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
