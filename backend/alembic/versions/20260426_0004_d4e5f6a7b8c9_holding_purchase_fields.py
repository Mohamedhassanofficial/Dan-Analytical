"""holding purchase fields — purchase_date + purchase_price

Adds two nullable columns to `portfolio_holdings` so the new Slide-#8
"Add to portfolio" modal can capture when the user bought a position and
at what price. Both nullable — pre-existing holdings (if any) keep NULL;
the API backfills `today` + `stocks.last_price` for new inserts.

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-04-26 00:00:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, Sequence[str], None] = "c3d4e5f6a7b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("portfolio_holdings", sa.Column("purchase_date", sa.Date))
    op.add_column("portfolio_holdings", sa.Column("purchase_price", sa.Numeric(14, 4)))


def downgrade() -> None:
    op.drop_column("portfolio_holdings", "purchase_price")
    op.drop_column("portfolio_holdings", "purchase_date")
