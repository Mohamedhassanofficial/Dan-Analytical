"""extended financial ratios — 16 new nullable columns on stocks

Adds the additional ratios Loay catalogued on slide 79 of the spec PDF:

  Liquidity      → current_ratio, quick_ratio, cash_ratio,
                   interest_coverage_ratio
  Efficiency     → asset_turnover, inventory_turnover,
                   receivables_turnover, payables_turnover
  Profitability  → roa, net_profit_margin, gross_profit_margin
  Per-Share      → book_value_per_share, revenue_per_share
  Shariah        → debt_to_market_cap, cash_to_assets,
                   receivables_to_assets

All nullable so existing rows survive the migration cleanly. The seed
backfills realistic values per sector.

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-04-27 00:00:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e5f6a7b8c9d0"
down_revision: Union[str, Sequence[str], None] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Liquidity
    op.add_column("stocks", sa.Column("current_ratio", sa.Numeric(10, 4)))
    op.add_column("stocks", sa.Column("quick_ratio", sa.Numeric(10, 4)))
    op.add_column("stocks", sa.Column("cash_ratio", sa.Numeric(10, 4)))
    op.add_column("stocks", sa.Column("interest_coverage_ratio", sa.Numeric(10, 4)))
    # Efficiency
    op.add_column("stocks", sa.Column("asset_turnover", sa.Numeric(10, 4)))
    op.add_column("stocks", sa.Column("inventory_turnover", sa.Numeric(10, 4)))
    op.add_column("stocks", sa.Column("receivables_turnover", sa.Numeric(10, 4)))
    op.add_column("stocks", sa.Column("payables_turnover", sa.Numeric(10, 4)))
    # Profitability
    op.add_column("stocks", sa.Column("roa", sa.Numeric(10, 6)))
    op.add_column("stocks", sa.Column("net_profit_margin", sa.Numeric(10, 6)))
    op.add_column("stocks", sa.Column("gross_profit_margin", sa.Numeric(10, 6)))
    # Per-Share
    op.add_column("stocks", sa.Column("book_value_per_share", sa.Numeric(14, 4)))
    op.add_column("stocks", sa.Column("revenue_per_share", sa.Numeric(14, 4)))
    # Shariah-Compliance
    op.add_column("stocks", sa.Column("debt_to_market_cap", sa.Numeric(10, 6)))
    op.add_column("stocks", sa.Column("cash_to_assets", sa.Numeric(10, 6)))
    op.add_column("stocks", sa.Column("receivables_to_assets", sa.Numeric(10, 6)))


def downgrade() -> None:
    for col in (
        "receivables_to_assets",
        "cash_to_assets",
        "debt_to_market_cap",
        "revenue_per_share",
        "book_value_per_share",
        "gross_profit_margin",
        "net_profit_margin",
        "roa",
        "payables_turnover",
        "receivables_turnover",
        "inventory_turnover",
        "asset_turnover",
        "interest_coverage_ratio",
        "cash_ratio",
        "quick_ratio",
        "current_ratio",
    ):
        op.drop_column("stocks", col)
