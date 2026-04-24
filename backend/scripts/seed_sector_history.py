"""
Seed `sector_index_daily` from Index-Data-From-28-02-2016-To26-02-2026.csv
(10 years, ~44,506 rows across 21 Tadawul sectors).

Run AFTER `seed_stocks` (which creates sectors). Re-runs are safe — conflicts
on (sector_id, trade_date) are ignored via ON CONFLICT DO NOTHING.

Usage (from backend/):
    python -m scripts.seed_sector_history
    python -m scripts.seed_sector_history --batch-size 5000
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.models import Sector, SectorIndexDaily  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INDEX_FILE = REPO_ROOT / "Index-Data-From-28-02-2016-To26-02-2026.csv"


def load_and_normalize(index_file: Path) -> pd.DataFrame:
    """Load the CSV and return a clean long-form DataFrame ready for insert."""
    df = pd.read_csv(index_file, encoding="utf-8-sig")
    df.columns = [str(c).strip() for c in df.columns]

    required = {"L.T. Date", "Sector Code", "Close"}
    missing = required - set(df.columns)
    if missing:
        raise RuntimeError(
            f"CSV is missing required columns: {missing}. Found: {list(df.columns)}"
        )

    df["trade_date"] = pd.to_datetime(df["L.T. Date"], format="%d/%m/%Y", errors="coerce")
    df = df.dropna(subset=["trade_date", "Sector Code", "Close"])
    df["sector_code"] = df["Sector Code"].astype(str).str.strip()
    df["close"] = pd.to_numeric(df["Close"], errors="coerce")
    df = df.dropna(subset=["close"])

    # Keep the last value if a (sector, date) pair appears twice
    df = df.sort_values(["sector_code", "trade_date"]).drop_duplicates(
        subset=["sector_code", "trade_date"], keep="last"
    )
    return df[["sector_code", "trade_date", "close"]].reset_index(drop=True)


def seed(index_file: Path = DEFAULT_INDEX_FILE, batch_size: int = 5000) -> int:
    df = load_and_normalize(index_file)
    print(f"Loaded {len(df):,} rows from {index_file.name}")
    print(f"  sectors: {df['sector_code'].nunique()}, "
          f"date range: {df['trade_date'].min().date()} → {df['trade_date'].max().date()}")

    total = 0
    with SessionLocal() as db:
        sector_map = {
            row.sector_code: row.id
            for row in db.execute(select(Sector)).scalars()
        }
        unknown = set(df["sector_code"]) - set(sector_map)
        if unknown:
            print(
                f"WARNING: {len(unknown)} sector codes in CSV are not in the sectors "
                f"table and will be skipped: {sorted(unknown)[:5]}..."
            )

        rows: list[dict] = []
        for _, r in df.iterrows():
            sid = sector_map.get(r["sector_code"])
            if sid is None:
                continue
            rows.append(
                {
                    "sector_id": sid,
                    "trade_date": r["trade_date"].date(),
                    "close": float(r["close"]),
                }
            )

        # Batched upsert — PG supports multi-row INSERT efficiently
        for start in range(0, len(rows), batch_size):
            batch = rows[start:start + batch_size]
            stmt = pg_insert(SectorIndexDaily).values(batch).on_conflict_do_nothing(
                index_elements=["sector_id", "trade_date"]
            )
            db.execute(stmt)
            total += len(batch)
            if (start // batch_size) % 5 == 0:
                print(f"  ...inserted {total:,} / {len(rows):,}")

        db.commit()
    return total


def main() -> int:
    ap = argparse.ArgumentParser(description="Seed 10-year Tadawul sector index history.")
    ap.add_argument("--file", type=Path, default=DEFAULT_INDEX_FILE)
    ap.add_argument("--batch-size", type=int, default=5000)
    args = ap.parse_args()

    if not args.file.exists():
        print(f"ERROR: index file not found: {args.file}", file=sys.stderr)
        return 1

    n = seed(args.file, args.batch_size)
    print(f"\n✓ sector_index_daily rows touched: {n:,}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
