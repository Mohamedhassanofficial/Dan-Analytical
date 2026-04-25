"""disclosure dates — balance sheet / income statement / latest dividend

Adds 3 nullable date columns to `stocks` to power the Screener's "last
updated" columns (Loay slide — Financial Ratios band):
  - last_balance_sheet_date   (fundamental disclosure)
  - last_income_statement_date (fundamental disclosure)
  - latest_dividend_date      (most recent cash dividend ex-date)

All nullable — disclosures are patchy per issuer.

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-04-25 00:00:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, Sequence[str], None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("stocks", sa.Column("last_balance_sheet_date", sa.Date))
    op.add_column("stocks", sa.Column("last_income_statement_date", sa.Date))
    op.add_column("stocks", sa.Column("latest_dividend_date", sa.Date))


def downgrade() -> None:
    for col in (
        "latest_dividend_date",
        "last_income_statement_date",
        "last_balance_sheet_date",
    ):
        op.drop_column("stocks", col)
