"""
Admin API endpoints — Phase A scope:
    - admin_config CRUD
    - Excel upload for sector historical data (template-validated)
    - Trigger-on-demand yfinance refresh

Every state-changing call writes to audit_log.
"""
from __future__ import annotations

import io
import json
import math
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import pandas as pd
from fastapi import APIRouter, File, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.api.deps import BootstrapOrAdminDep, DbDep
from app.db.models import AdminConfig, AuditLog, Sector, SectorIndexDaily, Stock
from app.schemas.admin import AdminConfigOut, AdminConfigUpdate, SectorUploadResult
from app.services.market_data import refresh_all
from app.services.stock_analytics import compute_risk_ranking
from app.services.stock_analytics import refresh_all as refresh_analytics_all

router = APIRouter(prefix="/admin", tags=["admin"])


# ---------------------------------------------------------------------------
# admin_config CRUD
# ---------------------------------------------------------------------------
def _decode(row: AdminConfig) -> AdminConfigOut:
    return AdminConfigOut(
        key=row.key,
        value=json.loads(row.value),
        value_type=row.value_type,  # type: ignore[arg-type]
        description_ar=row.description_ar,
        description_en=row.description_en,
        updated_at=row.updated_at,
    )


def _coerce(value: Any, value_type: str) -> Any:
    """Coerce an incoming value to the declared type; reject mismatches."""
    if value_type == "number":
        if not isinstance(value, (int, float)):
            raise HTTPException(422, "Expected a number.")
        return value
    if value_type == "bool":
        if not isinstance(value, bool):
            raise HTTPException(422, "Expected a boolean.")
        return value
    if value_type == "string":
        if not isinstance(value, str):
            raise HTTPException(422, "Expected a string.")
        return value
    if value_type == "json":
        return value  # accepted as-is
    raise HTTPException(422, f"Unknown value_type: {value_type}")


@router.get("/config", response_model=list[AdminConfigOut])
def list_config(db: DbDep, _: BootstrapOrAdminDep) -> list[AdminConfigOut]:
    rows = db.execute(select(AdminConfig).order_by(AdminConfig.key)).scalars().all()
    return [_decode(r) for r in rows]


@router.get("/config/{key}", response_model=AdminConfigOut)
def get_config(key: str, db: DbDep, _: BootstrapOrAdminDep) -> AdminConfigOut:
    row = db.get(AdminConfig, key)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Unknown config key: {key}")
    return _decode(row)


@router.put("/config/{key}", response_model=AdminConfigOut)
def update_config(
    key: str, payload: AdminConfigUpdate, db: DbDep, _: BootstrapOrAdminDep, request: Request
) -> AdminConfigOut:
    row = db.get(AdminConfig, key)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Unknown config key: {key}")

    coerced = _coerce(payload.value, row.value_type)
    old_value = row.value
    row.value = json.dumps(coerced)
    db.add(row)

    db.add(
        AuditLog(
            user_id=None,  # real user id lands in Phase B once auth is wired
            action="admin_config.update",
            resource_type="admin_config",
            resource_id=key,
            request_method=request.method,
            request_path=str(request.url.path),
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
            details={"old_value": json.loads(old_value), "new_value": coerced},
        )
    )
    db.commit()
    db.refresh(row)
    return _decode(row)


# ---------------------------------------------------------------------------
# Excel upload — sector historical data
# ---------------------------------------------------------------------------
EXPECTED_SECTOR_UPLOAD_COLS = {"Sector Code", "Date", "Close"}


@router.post(
    "/upload/sector-history",
    response_model=SectorUploadResult,
    status_code=status.HTTP_201_CREATED,
)
async def upload_sector_history(
    db: DbDep, _: BootstrapOrAdminDep, request: Request, file: UploadFile = File(...)
) -> SectorUploadResult:
    """
    Admin endpoint to append sector historical data from an Excel/CSV template.

    Required columns: `Sector Code`, `Date`, `Close`.
    Date format: ISO (YYYY-MM-DD) or `dd/mm/yyyy`.
    Unknown sectors are skipped with a warning; duplicates (same sector+date) are ignored.
    """
    content = await file.read()
    name = (file.filename or "").lower()
    try:
        if name.endswith(".csv"):
            df = pd.read_csv(io.BytesIO(content), encoding="utf-8-sig")
        else:
            df = pd.read_excel(io.BytesIO(content))
    except Exception as exc:
        raise HTTPException(400, f"Unable to parse uploaded file: {exc}") from exc

    df.columns = [str(c).strip() for c in df.columns]
    missing = EXPECTED_SECTOR_UPLOAD_COLS - set(df.columns)
    if missing:
        raise HTTPException(
            400,
            f"Template is missing required columns: {sorted(missing)}. "
            f"Expected exactly: {sorted(EXPECTED_SECTOR_UPLOAD_COLS)}",
        )

    # Parse dates flexibly
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce", dayfirst=True)
    df["Close"] = pd.to_numeric(df["Close"], errors="coerce")
    df["Sector Code"] = df["Sector Code"].astype(str).str.strip()

    warnings: list[str] = []
    rows_seen = len(df)
    df = df.dropna(subset=["Date", "Close", "Sector Code"])
    if rows_seen != len(df):
        warnings.append(f"{rows_seen - len(df)} rows had missing Date/Close/Sector Code and were skipped.")

    # Map sector_code → sector_id
    sector_map = {
        row.sector_code: row.id for row in db.execute(select(Sector)).scalars()
    }
    unknown = sorted(set(df["Sector Code"]) - set(sector_map))
    if unknown:
        warnings.append(f"Unknown sector codes skipped: {unknown}")

    rows: list[dict] = []
    for _, r in df.iterrows():
        sid = sector_map.get(r["Sector Code"])
        if sid is None:
            continue
        rows.append(
            {
                "sector_id": sid,
                "trade_date": r["Date"].date(),
                "close": float(r["Close"]),
            }
        )

    if not rows:
        return SectorUploadResult(
            filename=file.filename or "",
            rows_seen=rows_seen,
            rows_inserted=0,
            rows_skipped=rows_seen,
            warnings=warnings,
        )

    stmt = pg_insert(SectorIndexDaily).values(rows).on_conflict_do_nothing(
        index_elements=["sector_id", "trade_date"]
    )
    res = db.execute(stmt)
    inserted = res.rowcount or 0
    skipped = len(rows) - inserted

    db.add(
        AuditLog(
            user_id=None,
            action="admin.sector_upload",
            resource_type="sector_index_daily",
            resource_id=None,
            request_method=request.method,
            request_path=str(request.url.path),
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
            details={
                "filename": file.filename,
                "rows_seen": rows_seen,
                "rows_inserted": inserted,
                "rows_skipped": skipped,
                "warnings": warnings,
            },
        )
    )
    db.commit()

    return SectorUploadResult(
        filename=file.filename or "",
        rows_seen=rows_seen,
        rows_inserted=inserted,
        rows_skipped=skipped + (rows_seen - len(rows)),
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
# On-demand market data refresh trigger
# ---------------------------------------------------------------------------
@router.post("/refresh-prices")
def trigger_price_refresh(db: DbDep, _: BootstrapOrAdminDep) -> dict:
    """
    Kick off the yfinance price refresh synchronously. Returns a per-stock
    summary. In production, queue this to a background worker (RQ/Celery)
    instead of blocking the request.
    """
    summary = refresh_all(db, today=date.today())
    return {
        "stocks_processed": summary.stocks_processed,
        "total_rows_added": summary.total_rows_added,
        "failures": summary.failures,
        "failure_samples": [
            {"symbol": r.symbol, "error": r.error}
            for r in summary.per_stock
            if r.error
        ][:10],
    }


@router.post("/refresh-analytics")
def trigger_analytics_refresh(
    db: DbDep,
    _: BootstrapOrAdminDep,
    symbols: str | None = None,
    sleep_sec: float = 0.3,
) -> dict:
    """
    Kick off the per-stock analytics refresh synchronously — populates the
    14 indicator columns (β, σ, Sharpe, VaR, Risk Ranking, P/E, EPS, …)
    from yfinance.info + price history. Expect ~3 min for the full universe.

    Query params:
      symbols=2222.SR,1120.SR   limit to a subset (for smoke testing)
      sleep_sec=0.3             throttle between yfinance calls
    """
    sym_list = [s.strip() for s in symbols.split(",") if s.strip()] if symbols else None
    summary = refresh_analytics_all(db, symbols=sym_list, sleep_sec=sleep_sec)
    return {
        "stocks_processed": summary.stocks_processed,
        "stocks_updated": summary.stocks_updated,
        "fundamentals_populated": summary.fundamentals_populated,
        "failures": summary.failures,
        "failure_samples": [
            {"symbol": r.symbol, "error": r.error}
            for r in summary.per_stock
            if r.error
        ][:10],
    }


# ---------------------------------------------------------------------------
# Stock fundamentals — Excel upload (bypass yfinance rate limits)
# ---------------------------------------------------------------------------
# Admin fills in the 17-column template, uploads, we UPDATE stocks rows by
# Symbol. Mirrors the approved `Model-Cacluation-For-Excel-File.xlsx` column
# semantics so Loay can fill it in from Yahoo once and we're done.

FUNDAMENTALS_TEMPLATE = (
    Path(__file__).resolve().parents[3]
    / "assets" / "templates" / "stock_fundamentals_template.xlsx"
)

# Excel column label → Stock model attribute. Admins can rearrange columns
# or omit any; the parser looks up each known label case-insensitively.
# Values are decimals throughout (not %), matching the rest of the system.
FUNDAMENTALS_COLUMN_MAP: dict[str, str] = {
    "symbol":              "__symbol__",     # key, not a stored column
    "beta":                "beta",
    "daily volatility":    "daily_volatility",
    "annual volatility":   "annual_volatility",
    "sharp ratio":         "sharp_ratio",
    "sharpe ratio":        "sharp_ratio",     # common alias
    "var 1-day":           "var_95_daily",
    "var 1 day":           "var_95_daily",
    "var_95_daily":        "var_95_daily",
    "capm expected return": "capm_expected_return",
    "expected return":     "capm_expected_return",
    "p/e":                 "pe_ratio",
    "pe":                  "pe_ratio",
    "pe ratio":            "pe_ratio",
    "eps":                 "eps",
    "dividend yield":      "dividend_yield",
    "annual dividend rate": "annual_dividend_rate",
    "roe":                 "roe",
    "market to book":      "market_to_book",
    "m/b":                 "market_to_book",
    "fcf yield":           "fcf_yield",
    "leverage":            "leverage_ratio",
    "leverage ratio":      "leverage_ratio",
    "last price":          "last_price",
    "last price date":     "last_price_date",
}

# Subset of model attrs that store Decimals (for safe conversion).
DECIMAL_FIELDS = {
    "beta", "daily_volatility", "annual_volatility", "sharp_ratio",
    "var_95_daily", "capm_expected_return", "pe_ratio", "market_to_book",
    "roe", "fcf_yield", "leverage_ratio", "eps", "dividend_yield",
    "annual_dividend_rate", "last_price",
}


def _coerce_decimal(v: Any) -> Decimal | None:
    """Normalise any Excel cell value to Decimal or None."""
    if v is None or v == "":
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if math.isnan(f) or math.isinf(f):
        return None
    try:
        return Decimal(str(f))
    except (InvalidOperation, TypeError):
        return None


def _coerce_date(v: Any) -> date | None:
    if v is None or v == "":
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    try:
        return pd.to_datetime(v).date()
    except (ValueError, TypeError):
        return None


def _norm_symbol(raw: Any) -> str | None:
    """Accept '2222', 2222, '2222.SR', pad to 4 digits."""
    if raw is None or (isinstance(raw, float) and math.isnan(raw)):
        return None
    s = str(raw).strip().upper()
    if s.endswith(".SR"):
        s = s[:-3]
    # Numeric-looking → zero-pad to 4 digits (common Tadawul codes)
    if s.isdigit():
        return s.zfill(4)
    return s or None


@router.get("/upload/stock-fundamentals/template")
def download_fundamentals_template(_: BootstrapOrAdminDep) -> FileResponse:
    """Serve the blank Excel template for admin bulk-upload of fundamentals."""
    if not FUNDAMENTALS_TEMPLATE.exists():
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "Template file missing — run `python -m scripts.generate_fundamentals_template`.",
        )
    return FileResponse(
        FUNDAMENTALS_TEMPLATE,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename="stock_fundamentals_template.xlsx",
    )


@router.post(
    "/upload/stock-fundamentals",
    response_model=SectorUploadResult,
    status_code=status.HTTP_201_CREATED,
)
async def upload_stock_fundamentals(
    db: DbDep,
    _: BootstrapOrAdminDep,
    request: Request,
    file: UploadFile = File(...),
) -> SectorUploadResult:
    """
    Bulk-update stock fundamentals (the 12 financial + risk ratios per PPTX
    slide 83) from an uploaded Excel. One row per stock, keyed by `Symbol`.

    Columns are case-insensitive and flexible — missing columns leave the
    corresponding DB field untouched. Hint/comment rows whose `Symbol` cell
    starts with `#` are skipped so the generated template's help rows don't
    clobber data.

    After the update, `risk_ranking` is recomputed for every row that now has
    an `annual_volatility` so the PPTX slide 105 thresholds stay in sync.
    """
    content = await file.read()
    name = (file.filename or "").lower()
    try:
        if name.endswith(".csv"):
            df = pd.read_csv(io.BytesIO(content), encoding="utf-8-sig")
        else:
            df = pd.read_excel(io.BytesIO(content))
    except Exception as exc:
        raise HTTPException(400, f"Unable to parse uploaded file: {exc}") from exc

    if df.empty:
        raise HTTPException(400, "Uploaded file has no rows.")

    # Map each column header to a Stock attr; warn about unknown columns.
    col_to_field: dict[str, str] = {}
    unknown_cols: list[str] = []
    for col in df.columns:
        key = str(col).strip().lower()
        mapped = FUNDAMENTALS_COLUMN_MAP.get(key)
        if mapped:
            col_to_field[col] = mapped
        else:
            unknown_cols.append(str(col))

    if "__symbol__" not in col_to_field.values():
        raise HTTPException(
            400,
            "Uploaded file must include a 'Symbol' column (e.g. 2222 or 2222.SR).",
        )

    warnings: list[str] = []
    if unknown_cols:
        warnings.append(f"Ignored unknown columns: {unknown_cols}")

    # Prefetch all stocks once — cheaper than one SELECT per row.
    stocks_by_symbol: dict[str, Stock] = {
        s.symbol: s for s in db.execute(select(Stock)).scalars()
    }

    rows_seen = len(df)
    rows_updated = 0
    rows_skipped = 0
    unknown_symbols: list[str] = []

    for _idx, row in df.iterrows():
        raw_symbol: Any = None
        updates: dict[str, Any] = {}
        for col, field_name in col_to_field.items():
            val = row[col]
            if field_name == "__symbol__":
                raw_symbol = val
                continue
            if pd.isna(val):
                continue
            if field_name == "last_price_date":
                parsed = _coerce_date(val)
            elif field_name in DECIMAL_FIELDS:
                parsed = _coerce_decimal(val)
            else:
                parsed = val  # shouldn't happen given the map
            if parsed is not None:
                updates[field_name] = parsed

        sym = _norm_symbol(raw_symbol)
        if sym is None or sym.startswith("#"):
            # Hint / comment row — skip silently.
            rows_skipped += 1
            continue

        stock = stocks_by_symbol.get(sym)
        if stock is None:
            unknown_symbols.append(sym)
            rows_skipped += 1
            continue

        if not updates:
            rows_skipped += 1
            continue

        for k, v in updates.items():
            setattr(stock, k, v)

        # Recompute Risk Ranking from the (possibly just-updated) annual_volatility.
        stock.risk_ranking = compute_risk_ranking(stock.annual_volatility)
        stock.last_analytics_refresh = datetime.now(timezone.utc)
        rows_updated += 1

    if unknown_symbols:
        warnings.append(
            f"{len(unknown_symbols)} row(s) referenced unknown symbols; first 10: {unknown_symbols[:10]}"
        )

    db.add(
        AuditLog(
            user_id=None,
            action="admin.stock_fundamentals_upload",
            resource_type="stocks",
            resource_id=None,
            request_method=request.method,
            request_path=str(request.url.path),
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
            details={
                "filename": file.filename,
                "rows_seen": rows_seen,
                "rows_updated": rows_updated,
                "rows_skipped": rows_skipped,
                "columns_detected": list(col_to_field.keys()),
                "warnings": warnings,
            },
        )
    )
    db.commit()

    return SectorUploadResult(
        filename=file.filename or "",
        rows_seen=rows_seen,
        rows_inserted=rows_updated,
        rows_skipped=rows_skipped,
        warnings=warnings,
    )
