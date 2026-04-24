"""stock analytics columns — expanded indicator set per PPTX slides 82-91

Adds 14 new nullable columns to `stocks`:
  Risk: daily_volatility, sharp_ratio, var_95_daily, risk_ranking
  Financial: pe_ratio, market_to_book, roe, fcf_yield, leverage_ratio,
             eps, dividend_yield, annual_dividend_rate
  Price snapshot: last_price, last_price_date

All nullable — yfinance coverage for Tadawul is patchy; the Screener renders
missing values as "—" rather than failing.

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-04-24 00:00:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, Sequence[str], None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Risk indicators
    op.add_column("stocks", sa.Column("daily_volatility", sa.Numeric(10, 6)))
    op.add_column("stocks", sa.Column("sharp_ratio", sa.Numeric(10, 6)))
    op.add_column("stocks", sa.Column("var_95_daily", sa.Numeric(10, 6)))
    op.add_column("stocks", sa.Column("risk_ranking", sa.String(40)))
    # Financial indicators
    op.add_column("stocks", sa.Column("pe_ratio", sa.Numeric(14, 4)))
    op.add_column("stocks", sa.Column("market_to_book", sa.Numeric(14, 4)))
    op.add_column("stocks", sa.Column("roe", sa.Numeric(10, 6)))
    op.add_column("stocks", sa.Column("fcf_yield", sa.Numeric(10, 6)))
    op.add_column("stocks", sa.Column("leverage_ratio", sa.Numeric(10, 6)))
    op.add_column("stocks", sa.Column("eps", sa.Numeric(14, 4)))
    op.add_column("stocks", sa.Column("dividend_yield", sa.Numeric(10, 6)))
    op.add_column("stocks", sa.Column("annual_dividend_rate", sa.Numeric(14, 4)))
    # Price snapshot
    op.add_column("stocks", sa.Column("last_price", sa.Numeric(14, 4)))
    op.add_column("stocks", sa.Column("last_price_date", sa.Date))


def downgrade() -> None:
    for col in (
        "last_price_date",
        "last_price",
        "annual_dividend_rate",
        "dividend_yield",
        "eps",
        "leverage_ratio",
        "fcf_yield",
        "roe",
        "market_to_book",
        "pe_ratio",
        "risk_ranking",
        "var_95_daily",
        "sharp_ratio",
        "daily_volatility",
    ):
        op.drop_column("stocks", col)
