"""
Stocks / screener endpoints.

Exposes the Tadawul universe with its pre-computed analytics columns so the
frontend can render the screener table locally (only ~234 rows — no need to
paginate or filter server-side).
"""
from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import joinedload

from app.api.deps import CurrentUserDep, DbDep
from app.db.models import Sector, Stock
from app.schemas.stocks import SectorAveragesOut, SectorSummary, StockRow
from app.services.sector_analytics import compute_sector_averages

router = APIRouter(prefix="/stocks", tags=["stocks"])


def _d(v: Decimal | None) -> float | None:
    return float(v) if v is not None else None


@router.get("", response_model=list[StockRow])
def list_stocks(db: DbDep, _: CurrentUserDep) -> list[StockRow]:
    """Return every active stock with its identity, sector, and 14 indicators."""
    rows = db.execute(
        select(Stock)
        .options(joinedload(Stock.sector))
        .where(Stock.is_active.is_(True))
        .order_by(Stock.symbol)
    ).scalars().all()

    return [
        StockRow(
            symbol=s.symbol,
            ticker_suffix=s.ticker_suffix,
            name_ar=s.name_ar,
            name_en=s.name_en,
            industry_ar=s.industry_ar,
            industry_en=s.industry_en,
            sector_code=s.sector.sector_code if s.sector else None,
            # Risk
            beta=_d(s.beta),
            capm_expected_return=_d(s.capm_expected_return),
            daily_volatility=_d(s.daily_volatility),
            annual_volatility=_d(s.annual_volatility),
            sharp_ratio=_d(s.sharp_ratio),
            var_95_daily=_d(s.var_95_daily),
            risk_ranking=s.risk_ranking,
            # Financial
            pe_ratio=_d(s.pe_ratio),
            market_to_book=_d(s.market_to_book),
            roe=_d(s.roe),
            fcf_yield=_d(s.fcf_yield),
            leverage_ratio=_d(s.leverage_ratio),
            eps=_d(s.eps),
            dividend_yield=_d(s.dividend_yield),
            annual_dividend_rate=_d(s.annual_dividend_rate),
            # Price snapshot
            last_price=_d(s.last_price),
            last_price_date=s.last_price_date,
            last_analytics_refresh=s.last_analytics_refresh,
        )
        for s in rows
    ]


# ---------------------------------------------------------------------------
# Sector averages (Loay slide 83 — "احتساب متوسط أداء القطاع الصناعي")
# ---------------------------------------------------------------------------
@router.get("/sectors-summary", response_model=list[SectorSummary])
def list_sectors_summary(db: DbDep, _: CurrentUserDep) -> list[SectorSummary]:
    """
    Lightweight per-sector summary used to populate the sector picker on the
    Screener: code + bilingual name + count of active stocks.
    """
    rows = db.execute(
        select(
            Sector.sector_code,
            Sector.name_ar,
            Sector.name_en,
            func.count(Stock.id).label("stock_count"),
        )
        .join(Stock, Stock.sector_id == Sector.id, isouter=True)
        .where(Sector.is_active.is_(True))
        .group_by(Sector.id, Sector.sector_code, Sector.name_ar, Sector.name_en)
        .order_by(Sector.sector_code)
    ).all()
    return [
        SectorSummary(
            sector_code=r.sector_code,
            sector_name_ar=r.name_ar,
            sector_name_en=r.name_en,
            stock_count=int(r.stock_count or 0),
        )
        for r in rows
    ]


@router.get("/sector-averages", response_model=SectorAveragesOut)
def sector_averages(
    sector_code: str, db: DbDep, _: CurrentUserDep
) -> SectorAveragesOut:
    """
    Return the average of every analytical indicator across stocks in the
    given sector. Per Loay slide 83: "All analytical indicators for the
    industrial sector are computed on a sector-average basis (sum / count)."

    Risk Ranking is derived from the *averaged* annual_volatility using the
    same slide-105 thresholds applied to individual stocks.
    """
    result = compute_sector_averages(db, sector_code)
    if result is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Unknown sector: {sector_code}")
    return SectorAveragesOut(**result.to_dict())
