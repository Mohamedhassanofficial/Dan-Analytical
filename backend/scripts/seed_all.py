"""
One-shot: run every seed script in the correct order.

Usage (from backend/):
    python -m scripts.seed_all
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.seed_admin_config import seed as seed_admin_config  # noqa: E402
from scripts.seed_disclaimer import seed as seed_disclaimer  # noqa: E402
from scripts.seed_sector_history import seed as seed_sector_history  # noqa: E402
from scripts.seed_stocks import (  # noqa: E402
    DEFAULT_INDEX_FILE,
    DEFAULT_STOCK_FILE,
    seed_sectors,
    seed_stocks,
)
from scripts.seed_ui_labels import seed as seed_ui_labels  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402


def main() -> int:
    print("=" * 72)
    print("Tadawul Portfolio Optimizer — Phase A data seeding")
    print("=" * 72)

    with SessionLocal() as db:
        n_sectors = seed_sectors(db, DEFAULT_INDEX_FILE)
        print(f"\n[1/6] sectors upserted:           {n_sectors}")

        n_stocks = seed_stocks(db, DEFAULT_STOCK_FILE)
        print(f"[2/6] stocks upserted:            {n_stocks}")

    n_history = seed_sector_history(DEFAULT_INDEX_FILE)
    print(f"[3/6] sector_index_daily rows:    {n_history:,}")

    n_cfg = seed_admin_config()
    print(f"[4/6] admin_config defaults:      {n_cfg}")

    seed_disclaimer()
    print("[5/6] disclaimer v1 activated")

    n_labels = seed_ui_labels()
    print(f"[6/6] ui_labels seeded:           {n_labels}")

    print("\n✓ Seeding complete. Run `uvicorn app.main:app --reload` to start the API.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
