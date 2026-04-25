"""
Seed ~25 well-known Tadawul stocks with realistic analytics values so the
Screener renders a visually compelling demo:

  - 4 Conservative  (σ_annual ≤ 10%)
  - 7 Moderately Conservative  (≤ 20%)
  - 9 Aggressive  (≤ 30%)
  - 5 Very Aggressive  (> 30%)
  - 3 rows carry negative values (β / Sharpe / M/B) so the accountant-style
    red coloring rule is visible on-screen.

Values are plausible approximations of public data (Yahoo / Argaam) and are
clearly marked as DEMO seed — overwrite via the admin Excel upload when the
client provides real numbers.

Run (from backend/):
    python -m scripts.seed_demo_analytics
"""
from __future__ import annotations

import sys
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.models import Stock  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.services.stock_analytics import compute_risk_ranking  # noqa: E402


# (symbol, β, σ_daily, σ_annual, Sharpe, VaR, CAPM_μ,
#  P/E, EPS, DivYield, DivRate, ROE, M/B, FCF, Lev, LastPrice)
DEMO: list[tuple] = [
    # ── Conservative (σ ≤ 10%) ─────────────────────────────────────────────
    ("1120", 0.72, 0.0131, 0.0976,  0.18, 0.017, 0.084, 14.20, 4.89, 0.0301, 2.45, 0.2815, 3.05, 0.0482, 0.65, 69.45),
    ("1180", 0.68, 0.0126, 0.0938,  0.12, 0.016, 0.075, 11.10, 5.12, 0.0325, 3.20, 0.2420, 2.85, 0.0441, 0.58, 55.20),
    ("7010", 0.65, 0.0129, 0.0961,  0.08, 0.018, 0.072, 13.50, 2.80, 0.0410, 1.50, 0.1845, 2.10, 0.0537, 0.48, 37.80),
    ("1010", 0.80, 0.0134, 0.0999,  0.15, 0.017, 0.086, 13.00, 3.65, 0.0380, 1.95, 0.2100, 2.40, 0.0505, 0.62, 31.10),
    # ── Moderately Conservative (≤ 20%) ────────────────────────────────────
    ("2222", 0.85, 0.0167, 0.1243, -0.03, 0.025, 0.068, 17.09, 1.56, 0.0517, 1.33, 0.2172, 4.18, 0.0613, 0.21, 40.15),
    ("1050", 0.78, 0.0178, 0.1326,  0.14, 0.023, 0.079, 10.85, 6.25, 0.0401, 2.80, 0.1980, 1.92, 0.0498, 0.71, 44.90),
    ("8010", 0.88, 0.0197, 0.1468,  0.11, 0.028, 0.081, 15.40, 4.10, 0.0312, 1.85, 0.1640, 2.65, 0.0362, 0.18, 132.50),
    ("2280", 0.74, 0.0213, 0.1587,  0.09, 0.030, 0.070, 18.20, 3.05, 0.0258, 1.25, 0.1585, 2.28, 0.0324, 0.82, 58.40),
    ("4190", 0.92, 0.0235, 0.1751,  0.16, 0.034, 0.092, 16.70, 6.92, 0.0485, 5.60, 0.4510, 6.40, 0.0712, 0.24, 131.60),
    ("1150", 0.82, 0.0261, 0.1946,  0.10, 0.038, 0.080, 12.45, 1.98, 0.0289, 0.72, 0.1720, 1.55, 0.0440, 0.55, 29.75),
    ("2020", 0.85, 0.0268, 0.1998,  0.13, 0.040, 0.084, 14.80, 5.40, 0.0352, 2.90, 0.1955, 2.18, 0.0518, 0.41, 118.30),
    # ── Aggressive (≤ 30%) ─────────────────────────────────────────────────
    ("2010", 1.08, 0.0283, 0.2110,  0.07, 0.041, 0.097, 15.30, 4.28, 0.0455, 3.10, 0.1420, 1.78, 0.0382, 0.68, 72.20),
    ("2290", 0.95, 0.0304, 0.2266,  0.09, 0.046, 0.087, 19.80, 2.55, 0.0288, 1.45, 0.1265, 1.85, 0.0358, 0.52, 52.85),
    ("4003", 1.02, 0.0317, 0.2363,  0.05, 0.048, 0.094, 24.60, 3.82, 0.0195, 1.85, 0.2045, 4.10, 0.0521, 0.15, 94.10),
    ("7200", 1.05, 0.0326, 0.2430,  0.06, 0.049, 0.095, 19.40, 2.95, 0.0221, 1.25, 0.1580, 1.95, 0.0408, 0.73, 58.75),
    ("1303", 1.12, 0.0338, 0.2520,  0.10, 0.053, 0.103, 21.20, 2.10, 0.0185, 0.82, 0.1125, 1.68, 0.0352, 0.59, 45.30),
    ("6002", 0.95, 0.0357, 0.2661,  0.04, 0.055, 0.088, 22.80, 1.75, 0.0205, 1.05, 0.1382, 2.40, 0.0425, 0.36, 52.10),
    ("2060", 1.24, 0.0372, 0.2772,  0.08, 0.058, 0.110, 20.15, 2.84, 0.0170, 0.95, 0.1425, 1.82, 0.0289, 0.88, 37.40),
    ("4030", 1.00, 0.0381, 0.2840,  0.07, 0.060, 0.092, 17.95, 3.12, 0.0265, 1.65, 0.1750, 2.25, 0.0495, 0.44, 31.85),
    ("2270", 0.78, 0.0393, 0.2928,  0.03, 0.059, 0.076, 28.40, 1.28, 0.0115, 0.65, 0.0920, 1.45, 0.0218, 0.28, 198.60),
    # ── Very Aggressive (> 30%) ────────────────────────────────────────────
    ("4338", 1.38, 0.0422, 0.3145,  0.12, 0.068, 0.118, 10.20, 2.45, 0.0248, 1.20, 0.2180, 1.65, 0.0645, 1.85, 23.80),
    ("2380", 1.52, 0.0445, 0.3317, -0.08, 0.074, 0.128, -24.50, -1.12, 0.0000, 0.00, -0.0485, 0.92, -0.0120, 2.45, 18.30),
    ("4240", 1.28, 0.0458, 0.3413,  0.05, 0.072, 0.112, 32.60, 0.85, 0.0145, 0.55, 0.0620, 2.85, 0.0195, 1.20, 34.75),
    ("4164", 1.15, 0.0473, 0.3525,  0.09, 0.075, 0.104, 45.20, 1.20, 0.0180, 0.75, 0.0840, 3.20, 0.0278, 0.82, 128.40),
    ("2083", 1.42, 0.0489, 0.3645,  0.06, 0.077, 0.121, 28.70, 1.62, 0.0120, 0.55, 0.0920, 1.48, 0.0265, 1.55, 42.60),
]


COLUMNS = (
    "symbol beta daily_volatility annual_volatility sharp_ratio var_95_daily "
    "capm_expected_return pe_ratio eps dividend_yield annual_dividend_rate "
    "roe market_to_book fcf_yield leverage_ratio last_price"
).split()


def seed() -> int:
    today = date.today()
    now = datetime.now(timezone.utc)
    updated = 0
    missing: list[str] = []

    with SessionLocal() as db:
        for row in DEMO:
            values = dict(zip(COLUMNS, row))
            symbol = values.pop("symbol")
            stock = db.query(Stock).filter(Stock.symbol == symbol).first()
            if stock is None:
                missing.append(symbol)
                continue
            for k, v in values.items():
                setattr(stock, k, Decimal(str(v)))
            stock.last_price_date = today
            stock.risk_ranking = compute_risk_ranking(stock.annual_volatility)
            stock.last_analytics_refresh = now
            updated += 1
        db.commit()

    if missing:
        print(f"⚠️  symbols not found in DB (skipped): {missing}")
    return updated


if __name__ == "__main__":
    n = seed()
    print(f"✓ demo analytics seeded for {n} stocks")
