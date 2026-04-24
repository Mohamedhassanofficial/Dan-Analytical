"""
Seed the `sectors` and `stocks` tables from the committed data files:
  - Stock-List-Arabic-and-English.xlsx  (at repo root)
  - Index-Data-From-28-02-2016-To26-02-2026.csv (sector codes only, for the sectors table)

Idempotent: re-running upserts by `symbol` / `sector_code` instead of duplicating rows.

Usage (from backend/):
    python -m scripts.seed_stocks
    python -m scripts.seed_stocks --file /path/to/custom.xlsx
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

# Allow running as `python scripts/seed_stocks.py` from backend/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.models import Sector, Stock  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_STOCK_FILE = REPO_ROOT / "Stock-List-Arabic-and-English.xlsx"
DEFAULT_INDEX_FILE = REPO_ROOT / "Index-Data-From-28-02-2016-To26-02-2026.csv"


# ----------------------------------------------------------------------------
# Column detection — the file has both EN and AR columns; tolerate variants.
# ----------------------------------------------------------------------------
SYMBOL_CANDIDATES = ["Symbol Code", "Symbol", "Ticker", "رمز السهم", "الرمز"]
NAME_EN_CANDIDATES = ["Company Name", "Name (EN)", "Company Name EN", "Name"]
NAME_AR_CANDIDATES = [
    "اسم الشركة",
    "الاسم",
    "Company Name (AR)",
    "Company Name AR",
    "Name (AR)",
]
INDUSTRY_EN_CANDIDATES = ["Industry Type", "Industry", "Sector Name", "Sector"]
INDUSTRY_AR_CANDIDATES = ["نوع النشاط", "القطاع", "Industry (AR)"]
INDEX_CODE_CANDIDATES = ["Index Code", "Sector Code", "Tadawul Code"]


def _pick_column(df: pd.DataFrame, candidates: list[str]) -> str | None:
    """Return the first candidate column name that exists in df (case-insensitive)."""
    lower_cols = {c.lower(): c for c in df.columns}
    for cand in candidates:
        if cand.lower() in lower_cols:
            return lower_cols[cand.lower()]
    return None


# ----------------------------------------------------------------------------
# Sectors (derived from the Index CSV's distinct Sector Code values)
# ----------------------------------------------------------------------------
# Known Tadawul sector codes → human names (bilingual).
# The CSV only carries the code; we hydrate names from this fixed map. Admins
# can edit name_ar / name_en afterwards via the admin_config UI.
SECTOR_NAMES: dict[str, tuple[str, str]] = {
    "TASI": ("المؤشر العام للسوق", "Tadawul All Share Index"),
    "TENI": ("قطاع الطاقة", "Energy"),
    "TMTI": ("قطاع المواد الأساسية", "Materials"),
    "TCSI": ("قطاع السلع الرأسمالية", "Capital Goods"),
    "TRTI": ("قطاع النقل", "Transportation"),
    "TCDI": ("قطاع السلع الاستهلاكية الكمالية", "Consumer Discretionary"),
    "TCMI": ("قطاع الإعلام", "Media & Entertainment"),
    "TRSI": ("قطاع البيع التجزئة", "Retailing"),
    "TFBI": ("قطاع الأغذية", "Food & Beverages"),
    "TCSI2": ("قطاع المستلزمات الصحية", "Consumer Services"),
    "THCI": ("قطاع الرعاية الصحية", "Health Care Equipment & Svc"),
    "TPHI": ("قطاع الأدوية", "Pharma, Biotech & Life Sci"),
    "TBNI": ("قطاع البنوك", "Banks"),
    "TDFI": ("قطاع الخدمات المالية المتنوعة", "Diversified Financials"),
    "TINI": ("قطاع التأمين", "Insurance"),
    "TTSI": ("قطاع الاتصالات", "Telecommunication Services"),
    "TUTI": ("قطاع المرافق", "Utilities"),
    "TREI": ("قطاع الريت", "REITs"),
    "TRDI": ("قطاع إدارة وتطوير العقارات", "Real Estate Mgmt & Dev"),
    "TSWI": ("قطاع الخدمات التجارية والمهنية", "Commercial & Professional Svc"),
    "TFNI": ("قطاع الخدمات الاستهلاكية", "Consumer Services"),
}


def seed_sectors(db: Session, index_file: Path = DEFAULT_INDEX_FILE) -> int:
    """Upsert sectors found in the index CSV. Returns count inserted/updated."""
    df = pd.read_csv(index_file, encoding="utf-8-sig", usecols=["Sector Code"])
    codes = sorted(df["Sector Code"].dropna().astype(str).str.strip().unique())

    count = 0
    for code in codes:
        name_ar, name_en = SECTOR_NAMES.get(code, (code, code))
        stmt = pg_insert(Sector).values(
            sector_code=code,
            name_ar=name_ar,
            name_en=name_en,
            is_active=True,
        ).on_conflict_do_update(
            index_elements=["sector_code"],
            set_=dict(name_ar=name_ar, name_en=name_en, is_active=True),
        )
        db.execute(stmt)
        count += 1
    db.commit()
    return count


# ----------------------------------------------------------------------------
# Stocks (from the bilingual Excel file)
# ----------------------------------------------------------------------------
def seed_stocks(db: Session, stock_file: Path = DEFAULT_STOCK_FILE) -> int:
    df = pd.read_excel(stock_file)
    df.columns = [str(c).strip() for c in df.columns]

    col_symbol = _pick_column(df, SYMBOL_CANDIDATES)
    col_name_en = _pick_column(df, NAME_EN_CANDIDATES)
    col_name_ar = _pick_column(df, NAME_AR_CANDIDATES)
    col_industry_en = _pick_column(df, INDUSTRY_EN_CANDIDATES)
    col_industry_ar = _pick_column(df, INDUSTRY_AR_CANDIDATES)
    col_index = _pick_column(df, INDEX_CODE_CANDIDATES)

    print(f"Detected columns in {stock_file.name}: {list(df.columns)}")
    print(f"  symbol       → {col_symbol}")
    print(f"  name_en      → {col_name_en}")
    print(f"  name_ar      → {col_name_ar}")
    print(f"  industry_en  → {col_industry_en}")
    print(f"  industry_ar  → {col_industry_ar}")
    print(f"  index_code   → {col_index}")

    if col_symbol is None:
        raise RuntimeError("Stock list file is missing a symbol column; cannot seed.")

    # Map sector_code → sector_id in one query
    sector_map = {
        row.sector_code: row.id for row in db.execute(select(Sector)).scalars()
    }

    count = 0
    for _, row in df.iterrows():
        raw_symbol = row[col_symbol]
        if pd.isna(raw_symbol):
            continue
        symbol = str(int(raw_symbol)).zfill(4) if isinstance(raw_symbol, (int, float)) \
            else str(raw_symbol).strip().zfill(4)
        ticker = f"{symbol}.SR"

        index_code = (
            str(row[col_index]).strip() if col_index and not pd.isna(row[col_index]) else None
        )
        sector_id = sector_map.get(index_code) if index_code else None

        values = dict(
            symbol=symbol,
            ticker_suffix=ticker,
            name_en=(str(row[col_name_en]).strip() if col_name_en and not pd.isna(row[col_name_en]) else None),
            name_ar=(str(row[col_name_ar]).strip() if col_name_ar and not pd.isna(row[col_name_ar]) else None),
            industry_en=(str(row[col_industry_en]).strip() if col_industry_en and not pd.isna(row[col_industry_en]) else None),
            industry_ar=(str(row[col_industry_ar]).strip() if col_industry_ar and not pd.isna(row[col_industry_ar]) else None),
            sector_id=sector_id,
            is_active=True,
        )

        stmt = pg_insert(Stock).values(**values).on_conflict_do_update(
            index_elements=["symbol"],
            set_={k: v for k, v in values.items() if k != "symbol"},
        )
        db.execute(stmt)
        count += 1

    db.commit()
    return count


# ----------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser(description="Seed sectors + stocks from repo data files.")
    ap.add_argument("--stock-file", type=Path, default=DEFAULT_STOCK_FILE)
    ap.add_argument("--index-file", type=Path, default=DEFAULT_INDEX_FILE)
    args = ap.parse_args()

    if not args.stock_file.exists():
        print(f"ERROR: stock list file not found: {args.stock_file}", file=sys.stderr)
        return 1
    if not args.index_file.exists():
        print(f"ERROR: index CSV file not found: {args.index_file}", file=sys.stderr)
        return 1

    with SessionLocal() as db:
        n_sectors = seed_sectors(db, args.index_file)
        print(f"\n✓ Sectors upserted: {n_sectors}")
        n_stocks = seed_stocks(db, args.stock_file)
        print(f"✓ Stocks upserted:  {n_stocks}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
