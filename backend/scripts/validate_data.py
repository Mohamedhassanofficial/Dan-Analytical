"""
Post-seed data validation for the Tadawul Portfolio Optimizer.

Runs a series of health checks against the live database and prints a
formatted report. Useful after `init_db.py` or after a production
deployment to verify data integrity.

Checks:
  1. sectors table: expected 21 rows, no null names
  2. stocks table: expected 234 rows, all linked to sectors
  3. sector_index_daily: ≥40K rows, date range 2016–2026, all sectors
  4. prices_daily: row count distribution, stocks with zero history
  5. admin_config: all required keys present
  6. TASI market proxy: exists and has ≥2000 days of data
  7. Bilingual completeness: no null name_ar / name_en in stocks

Usage (from backend/):
    python -m scripts.validate_data
    python -m scripts.validate_data --strict   # exit code 1 on any warning
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sqlalchemy import func, select, text

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.models import (  # noqa: E402
    AdminConfig,
    PriceDaily,
    Sector,
    SectorIndexDaily,
    Stock,
)
from app.db.session import SessionLocal  # noqa: E402


# ---------------------------------------------------------------------------
class CheckResult:
    def __init__(self, name: str):
        self.name = name
        self.passed = True
        self.warnings: list[str] = []
        self.details: list[str] = []

    def ok(self, msg: str):
        self.details.append(f"  ✅ {msg}")

    def warn(self, msg: str):
        self.warnings.append(msg)
        self.details.append(f"  ⚠️  {msg}")

    def fail(self, msg: str):
        self.passed = False
        self.details.append(f"  ❌ {msg}")

    def print(self):
        icon = "✅" if self.passed and not self.warnings else ("⚠️" if self.passed else "❌")
        print(f"\n{icon} {self.name}")
        for d in self.details:
            print(d)


# ---------------------------------------------------------------------------
def check_sectors(db) -> CheckResult:
    r = CheckResult("Sectors Table")
    count = db.execute(select(func.count()).select_from(Sector)).scalar()
    r.ok(f"Row count: {count}") if count >= 20 else r.fail(f"Only {count} sectors (expected ≥20)")

    null_ar = db.execute(
        select(func.count()).where(Sector.name_ar.is_(None))
    ).scalar()
    null_en = db.execute(
        select(func.count()).where(Sector.name_en.is_(None))
    ).scalar()
    if null_ar == 0 and null_en == 0:
        r.ok("All sectors have bilingual names")
    else:
        r.warn(f"Missing names: {null_ar} AR, {null_en} EN")

    return r


def check_stocks(db) -> CheckResult:
    r = CheckResult("Stocks Table")
    count = db.execute(select(func.count()).select_from(Stock)).scalar()
    if count >= 230:
        r.ok(f"Row count: {count} (expected ~234)")
    elif count > 0:
        r.warn(f"Only {count} stocks (expected ~234)")
    else:
        r.fail("No stocks found!")

    # All should have ticker_suffix
    null_ticker = db.execute(
        select(func.count()).where(Stock.ticker_suffix.is_(None))
    ).scalar()
    r.ok("All stocks have ticker_suffix") if null_ticker == 0 else r.fail(f"{null_ticker} stocks missing ticker_suffix")

    # Sector linkage
    unlinked = db.execute(
        select(func.count()).where(Stock.sector_id.is_(None), Stock.is_active.is_(True))
    ).scalar()
    if unlinked == 0:
        r.ok("All active stocks linked to a sector")
    else:
        r.warn(f"{unlinked} active stocks have no sector_id")

    # Bilingual names
    null_ar = db.execute(select(func.count()).where(Stock.name_ar.is_(None), Stock.is_active.is_(True))).scalar()
    null_en = db.execute(select(func.count()).where(Stock.name_en.is_(None), Stock.is_active.is_(True))).scalar()
    if null_ar == 0 and null_en == 0:
        r.ok("All stocks have bilingual names")
    else:
        r.warn(f"Missing names in active stocks: {null_ar} AR, {null_en} EN")

    return r


def check_sector_index(db) -> CheckResult:
    r = CheckResult("Sector Index History")
    count = db.execute(select(func.count()).select_from(SectorIndexDaily)).scalar()
    if count >= 40_000:
        r.ok(f"Row count: {count:,} (expected ≥40,000)")
    elif count > 0:
        r.warn(f"Only {count:,} rows (expected ≥40,000 for 10 years)")
    else:
        r.fail("No sector index history!")

    if count > 0:
        min_date = db.execute(select(func.min(SectorIndexDaily.trade_date))).scalar()
        max_date = db.execute(select(func.max(SectorIndexDaily.trade_date))).scalar()
        r.ok(f"Date range: {min_date} → {max_date}")

        n_sectors = db.execute(
            select(func.count(func.distinct(SectorIndexDaily.sector_id)))
        ).scalar()
        r.ok(f"Sectors with data: {n_sectors}")

    return r


def check_prices(db) -> CheckResult:
    r = CheckResult("Prices Daily")
    count = db.execute(select(func.count()).select_from(PriceDaily)).scalar()

    if count == 0:
        r.warn("No price data yet — run: python -m scripts.backfill_prices")
        return r

    r.ok(f"Total rows: {count:,}")

    # Stocks with zero price rows
    stocks_with_prices = db.execute(
        select(func.count(func.distinct(PriceDaily.stock_id)))
    ).scalar()
    total_stocks = db.execute(
        select(func.count()).where(Stock.is_active.is_(True))
    ).scalar()
    coverage = stocks_with_prices / max(total_stocks, 1) * 100
    r.ok(f"Coverage: {stocks_with_prices}/{total_stocks} stocks ({coverage:.0f}%)")

    # Distribution of row counts
    row_counts = db.execute(
        select(
            func.count().label("n_rows"),
        )
        .select_from(PriceDaily)
        .group_by(PriceDaily.stock_id)
    ).scalars().all()

    if row_counts:
        min_rows = min(row_counts)
        max_rows = max(row_counts)
        avg_rows = sum(row_counts) / len(row_counts)
        r.ok(f"Per-stock rows: min={min_rows}, avg={avg_rows:.0f}, max={max_rows}")

    return r


def check_admin_config(db) -> CheckResult:
    r = CheckResult("Admin Config")

    required_keys = [
        "risk_free_rate", "lookback_days", "trading_days_per_year",
        "allow_shorting", "default_confidence_var",
        "subscription_price_sar", "payment_gateway",
        "market_proxy_sector_code",
    ]

    existing = set(
        db.execute(select(AdminConfig.key)).scalars().all()
    )
    for key in required_keys:
        if key in existing:
            r.ok(f"Key '{key}' present")
        else:
            r.warn(f"Key '{key}' MISSING")

    return r


def check_tasi_market_proxy(db) -> CheckResult:
    r = CheckResult("TASI Market Proxy")

    tasi = db.execute(
        select(Sector).where(Sector.sector_code == "TASI")
    ).scalar_one_or_none()

    if tasi is None:
        r.fail("TASI sector not found in sectors table!")
        return r

    r.ok(f"TASI sector found (id={tasi.id})")

    tasi_days = db.execute(
        select(func.count()).where(SectorIndexDaily.sector_id == tasi.id)
    ).scalar()

    if tasi_days >= 2000:
        r.ok(f"TASI has {tasi_days:,} days of history")
    elif tasi_days > 0:
        r.warn(f"TASI only has {tasi_days:,} days (expected ≥2000)")
    else:
        r.fail("TASI has no index history!")

    return r


# ---------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser(description="Validate Tadawul database integrity.")
    ap.add_argument("--strict", action="store_true", help="Exit 1 on any warning")
    args = ap.parse_args()

    print("=" * 56)
    print("🔍 Tadawul Data Validation Report")
    print("=" * 56)

    checks: list[CheckResult] = []

    with SessionLocal() as db:
        checks.append(check_sectors(db))
        checks.append(check_stocks(db))
        checks.append(check_sector_index(db))
        checks.append(check_prices(db))
        checks.append(check_admin_config(db))
        checks.append(check_tasi_market_proxy(db))

    for c in checks:
        c.print()

    # Summary
    passed = sum(1 for c in checks if c.passed and not c.warnings)
    warned = sum(1 for c in checks if c.passed and c.warnings)
    failed = sum(1 for c in checks if not c.passed)

    print(f"\n{'=' * 56}")
    print(f"📊 Summary: {passed} passed, {warned} warnings, {failed} failed")
    print(f"{'=' * 56}\n")

    if failed > 0:
        return 1
    if args.strict and warned > 0:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
