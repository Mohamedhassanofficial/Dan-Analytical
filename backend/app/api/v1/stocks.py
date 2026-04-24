"""
Stocks / screener endpoints.

Exposes the Tadawul universe with its pre-computed analytics columns so the
frontend can render the screener table locally (only ~234 rows — no need to
paginate or filter server-side).
"""
from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from app.api.deps import CurrentUserDep, DbDep
from app.db.models import Stock
from app.schemas.stocks import StockRow

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
