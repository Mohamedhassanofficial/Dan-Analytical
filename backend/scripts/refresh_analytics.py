"""
CLI entry point for the stock-analytics refresh.

Populates the 14 analytical columns (β, σ, Sharpe, VaR, Risk Ranking, P/E,
EPS, dividend yield, etc.) for every active Tadawul stock in the DB.

Usage (from backend/):
    python -m scripts.refresh_analytics                       # all active stocks
    python -m scripts.refresh_analytics --symbols 2222.SR,1120.SR,7010.SR
    python -m scripts.refresh_analytics --sleep-sec 0.1       # faster / riskier
    python -m scripts.refresh_analytics --as-of 2026-04-23    # treat this day as "today"
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.session import SessionLocal  # noqa: E402
from app.services.stock_analytics import refresh_all  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Refresh per-stock analytics (P/E, Sharpe, β, VaR, …) from yfinance."
    )
    ap.add_argument(
        "--symbols",
        type=str,
        default=None,
        help="Comma-separated Tadawul tickers (e.g. '2222.SR,1120.SR'). Default: all active.",
    )
    ap.add_argument(
        "--sleep-sec",
        type=float,
        default=0.3,
        help="Throttle between yfinance calls (default 0.3 s).",
    )
    ap.add_argument(
        "--as-of",
        type=date.fromisoformat,
        default=None,
        help="Treat this date as 'today' (defaults to most recent trade_date in prices_daily).",
    )
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-5s %(name)s — %(message)s",
    )

    symbols = None
    if args.symbols:
        symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]

    with SessionLocal() as db:
        summary = refresh_all(
            db,
            symbols=symbols,
            sleep_sec=args.sleep_sec,
            as_of=args.as_of,
        )

    print("\n" + "=" * 60)
    print(f"Stocks processed:         {summary.stocks_processed}")
    print(f"Stocks updated:           {summary.stocks_updated}")
    print(f"Fundamentals populated:   {summary.fundamentals_populated}")
    print(f"Failures:                 {summary.failures}")
    if summary.failures:
        print("\nFirst 10 failures:")
        for r in [x for x in summary.per_stock if x.error][:10]:
            print(f"  {r.symbol} ({r.ticker}): {r.error}")
    # Show a sample of successful updates
    ok = [r for r in summary.per_stock if r.updated_fields and not r.error][:5]
    if ok:
        print("\nSample updates:")
        for r in ok:
            print(f"  {r.ticker}: {', '.join(r.updated_fields[:6])}{'…' if len(r.updated_fields) > 6 else ''}")
    return 0 if summary.failures == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
