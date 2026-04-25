"""
Populate ALL active stocks (not just the curated 25) with sector-coherent
synthetic analytics so the Screener has real numbers across all 234 rows
for the demo.

Approach:
  1. Define a profile per sector: mean β, σ ranges, P/E ranges, etc., loosely
     informed by Saudi-market sector norms (Banks lower β + lower σ, Materials
     higher β, Real Estate higher σ, etc.)
  2. For each stock, sample within its sector's profile using a deterministic
     seed (so re-runs produce identical numbers).
  3. Risk Ranking is derived from the sampled annual_volatility — so the
     spread across the universe matches the spec's expected distribution.
  4. Idempotent: re-running overwrites all values with the same numbers.

This is DEMO data. Production replaces it via the admin Excel upload
(`/api/v1/admin/upload/stock-fundamentals`).
"""
from __future__ import annotations

import sys
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

import numpy as np
from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.models import Stock  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.services.stock_analytics import compute_risk_ranking  # noqa: E402


# ── Sector profiles ────────────────────────────────────────────────────────
# Each profile is the sampling parameters for that sector. Wide ranges for
# emerging-market / cyclical sectors; tight ranges for utilities / banks.
#
# Keys: sector_code → dict with parameter ranges.
PROFILE_DEFAULT = {
    "beta": (0.8, 1.20),
    "ann_vol": (0.20, 0.32),
    "capm_mu": (0.06, 0.11),
    "pe": (15.0, 28.0),
    "eps": (0.5, 4.0),
    "div_yield": (0.005, 0.045),
    "div_rate": (0.2, 2.5),
    "roe": (0.05, 0.18),
    "mb": (1.5, 3.5),
    "fcf_yield": (0.01, 0.06),
    "leverage": (0.20, 0.80),
    "last_price": (15.0, 80.0),
}

PROFILES: dict[str, dict[str, tuple[float, float]]] = {
    # Conservative / lower-vol sectors
    "TBNI": {  # Banks
        "beta": (0.55, 0.85),  "ann_vol": (0.09, 0.14),
        "capm_mu": (0.07, 0.11), "pe": (10.0, 16.0), "eps": (2.5, 6.5),
        "div_yield": (0.025, 0.045), "div_rate": (1.5, 3.5),
        "roe": (0.18, 0.30),  "mb": (2.0, 3.5), "fcf_yield": (0.04, 0.07),
        "leverage": (0.50, 0.85), "last_price": (25.0, 90.0),
    },
    "TTSI": {  # Telecom
        "beta": (0.55, 0.80), "ann_vol": (0.09, 0.13),
        "capm_mu": (0.06, 0.10), "pe": (12.0, 18.0), "eps": (2.0, 4.5),
        "div_yield": (0.030, 0.055), "div_rate": (1.0, 2.5),
        "roe": (0.14, 0.22), "mb": (1.8, 3.0), "fcf_yield": (0.04, 0.07),
        "leverage": (0.30, 0.65), "last_price": (28.0, 50.0),
    },
    "TUTI": {  # Utilities
        "beta": (0.50, 0.75), "ann_vol": (0.10, 0.15),
        "capm_mu": (0.05, 0.09), "pe": (12.0, 22.0), "eps": (1.0, 3.0),
        "div_yield": (0.030, 0.060), "div_rate": (0.8, 2.0),
        "roe": (0.08, 0.16), "mb": (1.2, 2.4), "fcf_yield": (0.03, 0.06),
        "leverage": (0.45, 0.85), "last_price": (18.0, 30.0),
    },
    # Moderate-vol sectors
    "TENI": {  # Energy
        "beta": (0.75, 1.05), "ann_vol": (0.13, 0.20),
        "capm_mu": (0.07, 0.11), "pe": (12.0, 20.0), "eps": (1.0, 2.5),
        "div_yield": (0.040, 0.065), "div_rate": (0.8, 2.0),
        "roe": (0.15, 0.25), "mb": (3.0, 5.5), "fcf_yield": (0.05, 0.09),
        "leverage": (0.15, 0.30), "last_price": (25.0, 50.0),
    },
    "TFBI": {  # Food & Beverages
        "beta": (0.65, 0.95), "ann_vol": (0.13, 0.21),
        "capm_mu": (0.06, 0.10), "pe": (15.0, 28.0), "eps": (1.5, 4.0),
        "div_yield": (0.018, 0.040), "div_rate": (0.5, 2.0),
        "roe": (0.10, 0.20), "mb": (1.5, 3.5), "fcf_yield": (0.025, 0.055),
        "leverage": (0.40, 0.85), "last_price": (40.0, 200.0),
    },
    "TRTI": {  # Transportation
        "beta": (0.85, 1.15), "ann_vol": (0.18, 0.28),
        "capm_mu": (0.07, 0.11), "pe": (14.0, 25.0), "eps": (1.0, 3.5),
        "div_yield": (0.015, 0.040), "div_rate": (0.4, 1.8),
        "roe": (0.10, 0.20), "mb": (1.5, 3.0), "fcf_yield": (0.025, 0.055),
        "leverage": (0.40, 0.90), "last_price": (20.0, 60.0),
    },
    # Higher-vol sectors
    "TMTI": {  # Materials (largest sector — chemicals/metals)
        "beta": (0.95, 1.30), "ann_vol": (0.18, 0.28),
        "capm_mu": (0.07, 0.12), "pe": (12.0, 26.0), "eps": (0.8, 5.0),
        "div_yield": (0.020, 0.055), "div_rate": (0.5, 3.0),
        "roe": (0.08, 0.20), "mb": (1.0, 2.5), "fcf_yield": (0.020, 0.060),
        "leverage": (0.40, 0.95), "last_price": (15.0, 110.0),
    },
    "TCSI": {  # Capital Goods
        "beta": (0.95, 1.30), "ann_vol": (0.20, 0.30),
        "capm_mu": (0.08, 0.12), "pe": (15.0, 28.0), "eps": (0.8, 3.0),
        "div_yield": (0.012, 0.035), "div_rate": (0.3, 1.5),
        "roe": (0.07, 0.16), "mb": (1.2, 2.5), "fcf_yield": (0.020, 0.050),
        "leverage": (0.45, 0.95), "last_price": (15.0, 50.0),
    },
    "TDFI": {  # Diversified Financials
        "beta": (0.85, 1.15), "ann_vol": (0.16, 0.26),
        "capm_mu": (0.07, 0.11), "pe": (12.0, 22.0), "eps": (0.8, 3.0),
        "div_yield": (0.020, 0.045), "div_rate": (0.3, 1.5),
        "roe": (0.09, 0.20), "mb": (1.2, 2.8), "fcf_yield": (0.025, 0.055),
        "leverage": (0.55, 0.90), "last_price": (15.0, 50.0),
    },
    "TISI": {  # Insurance
        "beta": (0.85, 1.15), "ann_vol": (0.18, 0.28),
        "capm_mu": (0.07, 0.11), "pe": (14.0, 24.0), "eps": (0.5, 2.5),
        "div_yield": (0.015, 0.035), "div_rate": (0.3, 1.2),
        "roe": (0.08, 0.18), "mb": (1.5, 2.8), "fcf_yield": (0.025, 0.055),
        "leverage": (0.20, 0.50), "last_price": (20.0, 80.0),
    },
    # Aggressive / very aggressive sectors
    "TRMI": {  # Real Estate Management
        "beta": (1.10, 1.45), "ann_vol": (0.28, 0.40),
        "capm_mu": (0.08, 0.13), "pe": (12.0, 30.0), "eps": (0.5, 2.5),
        "div_yield": (0.015, 0.035), "div_rate": (0.3, 1.2),
        "roe": (0.05, 0.18), "mb": (0.9, 2.2), "fcf_yield": (0.02, 0.07),
        "leverage": (0.80, 1.50), "last_price": (15.0, 40.0),
    },
    "TRLI": {  # REITs
        "beta": (0.85, 1.10), "ann_vol": (0.16, 0.24),
        "capm_mu": (0.06, 0.10), "pe": (14.0, 22.0), "eps": (0.4, 1.5),
        "div_yield": (0.045, 0.075), "div_rate": (0.5, 1.5),
        "roe": (0.06, 0.12), "mb": (0.8, 1.4), "fcf_yield": (0.04, 0.08),
        "leverage": (0.40, 0.90), "last_price": (8.0, 14.0),
    },
    "TPBI": {  # Pharma/Biotech
        "beta": (1.00, 1.30), "ann_vol": (0.24, 0.36),
        "capm_mu": (0.08, 0.12), "pe": (20.0, 45.0), "eps": (0.5, 3.0),
        "div_yield": (0.005, 0.025), "div_rate": (0.1, 1.0),
        "roe": (0.10, 0.20), "mb": (3.0, 7.0), "fcf_yield": (0.020, 0.050),
        "leverage": (0.20, 0.60), "last_price": (40.0, 130.0),
    },
}


def _sample(rng: np.random.Generator, profile: dict, key: str) -> float:
    lo, hi = profile.get(key, PROFILE_DEFAULT[key])
    return float(rng.uniform(lo, hi))


def seed() -> int:
    today = date.today()
    now = datetime.now(timezone.utc)
    updated = 0

    with SessionLocal() as db:
        stocks = db.execute(
            select(Stock).where(Stock.is_active.is_(True))
        ).scalars().all()

        for s in stocks:
            sector_code = s.sector.sector_code if s.sector else None
            profile = PROFILES.get(sector_code or "", PROFILE_DEFAULT)

            # Deterministic per-stock seed → re-runs produce identical numbers
            rng = np.random.default_rng(int(s.symbol) if s.symbol.isdigit() else hash(s.symbol) % 10**8)

            beta = _sample(rng, profile, "beta")
            ann_vol = _sample(rng, profile, "ann_vol")
            daily_vol = ann_vol / float(np.sqrt(252))
            capm_mu = _sample(rng, profile, "capm_mu")
            sharpe = (capm_mu - 0.0475) / max(ann_vol, 0.001)
            # Parametric VaR 95% 1-day (μ - z·σ); z=1.6449
            var_1d = max(0.0, -(capm_mu / 252 - 1.6449 * daily_vol))
            pe = _sample(rng, profile, "pe")
            eps = _sample(rng, profile, "eps")
            div_yield = _sample(rng, profile, "div_yield")
            div_rate = _sample(rng, profile, "div_rate")
            roe = _sample(rng, profile, "roe")
            mb = _sample(rng, profile, "mb")
            fcf_yield = _sample(rng, profile, "fcf_yield")
            leverage = _sample(rng, profile, "leverage")
            last_price = _sample(rng, profile, "last_price")

            # Inject a few negatives (~10% of stocks) for visual variety on the
            # "negative number = red" coloring rule. Cyclical sectors more likely.
            if sector_code in ("TMTI", "TRMI", "TCSI", "TPBI") and rng.random() < 0.18:
                pe = -abs(pe) * rng.uniform(0.2, 0.8)  # loss-making P/E
                eps = -abs(eps) * rng.uniform(0.3, 0.9)
            if rng.random() < 0.05:
                sharpe = -abs(sharpe) * rng.uniform(0.1, 0.5)

            s.beta = Decimal(str(round(beta, 6)))
            s.annual_volatility = Decimal(str(round(ann_vol, 6)))
            s.daily_volatility = Decimal(str(round(daily_vol, 6)))
            s.capm_expected_return = Decimal(str(round(capm_mu, 6)))
            s.sharp_ratio = Decimal(str(round(sharpe, 6)))
            s.var_95_daily = Decimal(str(round(var_1d, 6)))
            s.pe_ratio = Decimal(str(round(pe, 4)))
            s.eps = Decimal(str(round(eps, 4)))
            s.dividend_yield = Decimal(str(round(div_yield, 6)))
            s.annual_dividend_rate = Decimal(str(round(div_rate, 4)))
            s.roe = Decimal(str(round(roe, 6)))
            s.market_to_book = Decimal(str(round(mb, 4)))
            s.fcf_yield = Decimal(str(round(fcf_yield, 6)))
            s.leverage_ratio = Decimal(str(round(leverage, 6)))
            s.last_price = Decimal(str(round(last_price, 4)))
            s.last_price_date = today
            s.risk_ranking = compute_risk_ranking(s.annual_volatility)
            s.last_analytics_refresh = now

            updated += 1

        db.commit()

    return updated


if __name__ == "__main__":
    n = seed()
    print(f"✓ analytics seeded for {n} stocks (full Tadawul universe)")
