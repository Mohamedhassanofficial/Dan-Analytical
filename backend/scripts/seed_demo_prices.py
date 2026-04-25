"""
Demo-only synthetic price history.

Generates 3 years (≈ 756 trading days) of statistically coherent daily prices
for every stock that already has `annual_volatility` + `capm_expected_return`
set (i.e. the 25 demo stocks from `seed_demo_analytics`). Parameters:

  μ_daily = capm_expected_return / 252
  σ_daily = annual_volatility / sqrt(252)
  price[t+1] = price[t] * exp(N(μ_daily, σ_daily²))
  starting price = stock.last_price (or 50.0 if null)

Purpose: unblocks `POST /portfolio/{id}/compute` for the video demo without
requiring yfinance (which is rate-limiting Tadawul tickers). The Markowitz
optimizer then runs on synthetic-but-plausible data — same math path
production will use once real prices land.

Run (from backend/):
    python -m scripts.seed_demo_prices
"""
from __future__ import annotations

import sys
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import numpy as np
from sqlalchemy import delete, select

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.models import PriceDaily, Stock  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402


DAYS = 756          # ~3 years of trading
SEED_BASE = 20260424


def _business_days(n: int, end: date) -> list[date]:
    """Return n trading days ending at `end` (Sun–Thu per Tadawul, but we use
    Mon–Fri here for simplicity — the solver only cares about sequence, not
    weekday labels)."""
    days: list[date] = []
    d = end
    while len(days) < n:
        if d.weekday() < 5:  # Mon-Fri
            days.append(d)
        d -= timedelta(days=1)
    days.reverse()
    return days


def seed() -> int:
    today = date.today()
    dates = _business_days(DAYS, today)

    total_rows = 0

    with SessionLocal() as db:
        # Only stocks that already have analytics populated (the 25 demo ones).
        stocks = db.execute(
            select(Stock).where(
                Stock.annual_volatility.is_not(None),
                Stock.capm_expected_return.is_not(None),
            )
        ).scalars().all()

        for i, s in enumerate(stocks):
            ann_vol = float(s.annual_volatility)
            ann_mu = float(s.capm_expected_return)
            daily_vol = ann_vol / np.sqrt(252)
            daily_mu = ann_mu / 252
            start_price = float(s.last_price) if s.last_price else 50.0

            # Deterministic seed per stock so re-runs produce identical series
            rng = np.random.default_rng(SEED_BASE + i)
            returns = rng.normal(daily_mu, daily_vol, size=DAYS)
            log_prices = np.log(start_price) + np.cumsum(returns)
            prices = np.exp(log_prices)

            # Wipe any existing prices for this stock (idempotent re-run)
            db.execute(delete(PriceDaily).where(PriceDaily.stock_id == s.id))

            rows = [
                {
                    "stock_id": s.id,
                    "trade_date": d,
                    "open": Decimal(str(round(p, 4))),
                    "high": Decimal(str(round(p * 1.005, 4))),
                    "low": Decimal(str(round(p * 0.995, 4))),
                    "close": Decimal(str(round(p, 4))),
                    "adj_close": Decimal(str(round(p, 4))),
                    "volume": int(100_000 + rng.integers(0, 500_000)),
                }
                for d, p in zip(dates, prices)
            ]
            db.execute(PriceDaily.__table__.insert(), rows)
            total_rows += len(rows)

        # Also synthesise a TASI index series from the mean of all the stock
        # price series so the CAPM β regression has a real market proxy.
        from app.db.models import Sector, SectorIndexDaily  # noqa: E402
        tasi = db.execute(select(Sector).where(Sector.sector_code == "TASI")).scalar_one_or_none()
        if tasi is not None:
            # Build market index as average of stock daily returns, compound into prices
            returns_matrix = []
            for i, _s in enumerate(stocks):
                rng = np.random.default_rng(SEED_BASE + i)
                returns_matrix.append(rng.normal(
                    float(_s.capm_expected_return) / 252,
                    float(_s.annual_volatility) / np.sqrt(252),
                    size=DAYS,
                ))
            market_returns = np.mean(np.array(returns_matrix), axis=0)
            market_prices = 10000.0 * np.exp(np.cumsum(market_returns))

            # Delete existing TASI rows for our date range and insert fresh
            db.execute(
                delete(SectorIndexDaily)
                .where(SectorIndexDaily.sector_id == tasi.id)
                .where(SectorIndexDaily.trade_date.in_(dates))
            )
            db.execute(SectorIndexDaily.__table__.insert(), [
                {"sector_id": tasi.id, "trade_date": d, "close": Decimal(str(round(p, 4)))}
                for d, p in zip(dates, market_prices)
            ])

        db.commit()

    return total_rows


if __name__ == "__main__":
    n = seed()
    print(f"✓ seeded {n:,} synthetic daily price rows for {n // DAYS} stocks")
