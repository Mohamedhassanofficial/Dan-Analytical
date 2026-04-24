"""initial schema

Revision ID: a1b2c3d4e5f6
Revises:
Create Date: 2026-04-24 00:00:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import INET, JSONB


revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ------------------------------------------------------------------ users
    op.create_table(
        "users",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("national_id", sa.String(10), nullable=False),
        sa.Column("mobile", sa.String(20), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("full_name_ar", sa.String(255)),
        sa.Column("full_name_en", sa.String(255)),
        sa.Column("preferred_locale", sa.String(5), nullable=False, server_default="ar"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("is_admin", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("disclaimer_accepted_at", sa.DateTime(timezone=True)),
        sa.Column("last_login_at", sa.DateTime(timezone=True)),
        sa.Column("last_login_ip", INET),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("national_id", name="uq_users_national_id"),
        sa.UniqueConstraint("mobile", name="uq_users_mobile"),
        sa.UniqueConstraint("email", name="uq_users_email"),
        sa.CheckConstraint("char_length(national_id) = 10", name="ck_users_national_id_length"),
        sa.CheckConstraint(
            "preferred_locale IN ('ar', 'en')", name="ck_users_preferred_locale_enum"
        ),
    )

    # ----------------------------------------------------------- subscriptions
    op.create_table(
        "subscriptions",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column(
            "user_id",
            sa.BigInteger,
            sa.ForeignKey("users.id", ondelete="CASCADE", name="fk_subscriptions_user_id_users"),
            nullable=False,
        ),
        sa.Column("gateway", sa.String(20), nullable=False),
        sa.Column("gateway_transaction_id", sa.String(128)),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="SAR"),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True)),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("raw_gateway_payload", JSONB),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "gateway_transaction_id", name="uq_subscriptions_gateway_transaction_id"
        ),
        sa.CheckConstraint(
            "status IN ('pending','completed','failed','refunded')",
            name="ck_subscriptions_status_enum",
        ),
        sa.CheckConstraint(
            "gateway IN ('stcpay','paytabs')", name="ck_subscriptions_gateway_enum"
        ),
    )
    op.create_index("ix_subscriptions_user_id", "subscriptions", ["user_id"])
    op.create_index(
        "ix_subscriptions_user_expires", "subscriptions", ["user_id", "expires_at"]
    )

    # ---------------------------------------------------- disclaimer_versions
    op.create_table(
        "disclaimer_versions",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("version", sa.String(20), nullable=False),
        sa.Column("body_ar", sa.Text, nullable=False),
        sa.Column("body_en", sa.Text, nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("version", name="uq_disclaimer_versions_version"),
    )

    # -------------------------------------- user_disclaimer_acceptances
    op.create_table(
        "user_disclaimer_acceptances",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column(
            "user_id",
            sa.BigInteger,
            sa.ForeignKey(
                "users.id",
                ondelete="CASCADE",
                name="fk_user_disclaimer_acceptances_user_id_users",
            ),
            nullable=False,
        ),
        sa.Column(
            "disclaimer_id",
            sa.Integer,
            sa.ForeignKey(
                "disclaimer_versions.id",
                name="fk_uda_disclaimer_id_disclaimer_versions",
            ),
            nullable=False,
        ),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ip_address", INET),
        sa.UniqueConstraint(
            "user_id", "disclaimer_id", name="user_disclaimer_unique"
        ),
    )
    op.create_index(
        "ix_user_disclaimer_acceptances_user_id",
        "user_disclaimer_acceptances",
        ["user_id"],
    )

    # ---------------------------------------------------------------- sectors
    op.create_table(
        "sectors",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("sector_code", sa.String(10), nullable=False),
        sa.Column("name_ar", sa.String(255), nullable=False),
        sa.Column("name_en", sa.String(255), nullable=False),
        sa.Column("description_ar", sa.Text),
        sa.Column("description_en", sa.Text),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("sector_code", name="uq_sectors_sector_code"),
    )

    # ----------------------------------------------------------------- stocks
    op.create_table(
        "stocks",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("symbol", sa.String(10), nullable=False),
        sa.Column("ticker_suffix", sa.String(12), nullable=False),
        sa.Column("name_ar", sa.String(255)),
        sa.Column("name_en", sa.String(255)),
        sa.Column("industry_ar", sa.String(255)),
        sa.Column("industry_en", sa.String(255)),
        sa.Column(
            "sector_id",
            sa.Integer,
            sa.ForeignKey("sectors.id", name="fk_stocks_sector_id_sectors"),
        ),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("beta", sa.Numeric(10, 6)),
        sa.Column("capm_expected_return", sa.Numeric(10, 6)),
        sa.Column("annual_volatility", sa.Numeric(10, 6)),
        sa.Column("last_analytics_refresh", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("symbol", name="uq_stocks_symbol"),
        sa.UniqueConstraint("ticker_suffix", name="uq_stocks_ticker_suffix"),
    )
    op.create_index("ix_stocks_sector_id", "stocks", ["sector_id"])

    # ---------------------------------------------------------- prices_daily
    op.create_table(
        "prices_daily",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column(
            "stock_id",
            sa.Integer,
            sa.ForeignKey(
                "stocks.id", ondelete="CASCADE", name="fk_prices_daily_stock_id_stocks"
            ),
            nullable=False,
        ),
        sa.Column("trade_date", sa.Date, nullable=False),
        sa.Column("open", sa.Numeric(14, 4)),
        sa.Column("high", sa.Numeric(14, 4)),
        sa.Column("low", sa.Numeric(14, 4)),
        sa.Column("close", sa.Numeric(14, 4)),
        sa.Column("adj_close", sa.Numeric(14, 4)),
        sa.Column("volume", sa.BigInteger),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("stock_id", "trade_date", name="stock_date_unique"),
    )
    op.create_index(
        "ix_prices_daily_stock_date", "prices_daily", ["stock_id", "trade_date"]
    )
    op.create_index("ix_prices_daily_date", "prices_daily", ["trade_date"])

    # -------------------------------------------------- sector_index_daily
    op.create_table(
        "sector_index_daily",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column(
            "sector_id",
            sa.Integer,
            sa.ForeignKey(
                "sectors.id",
                ondelete="CASCADE",
                name="fk_sector_index_daily_sector_id_sectors",
            ),
            nullable=False,
        ),
        sa.Column("trade_date", sa.Date, nullable=False),
        sa.Column("close", sa.Numeric(14, 4), nullable=False),
        sa.UniqueConstraint("sector_id", "trade_date", name="sector_date_unique"),
    )
    op.create_index(
        "ix_sector_index_daily_sector_date",
        "sector_index_daily",
        ["sector_id", "trade_date"],
    )

    # ------------------------------------------------------------ portfolios
    op.create_table(
        "portfolios",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column(
            "user_id",
            sa.BigInteger,
            sa.ForeignKey("users.id", ondelete="CASCADE", name="fk_portfolios_user_id_users"),
            nullable=False,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("initial_capital", sa.Numeric(18, 2)),
        sa.Column("target_loss_threshold", sa.Numeric(10, 6)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_portfolios_user_id", "portfolios", ["user_id"])

    # --------------------------------------------------- portfolio_holdings
    op.create_table(
        "portfolio_holdings",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column(
            "portfolio_id",
            sa.BigInteger,
            sa.ForeignKey(
                "portfolios.id",
                ondelete="CASCADE",
                name="fk_portfolio_holdings_portfolio_id_portfolios",
            ),
            nullable=False,
        ),
        sa.Column(
            "stock_id",
            sa.Integer,
            sa.ForeignKey("stocks.id", name="fk_portfolio_holdings_stock_id_stocks"),
            nullable=False,
        ),
        sa.Column("weight", sa.Numeric(10, 6), nullable=False),
        sa.Column("shares", sa.Numeric(18, 4)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("portfolio_id", "stock_id", name="portfolio_stock_unique"),
        sa.CheckConstraint(
            "weight >= 0 AND weight <= 1", name="ck_portfolio_holdings_weight_bounds"
        ),
    )

    # ------------------------------------------------------ portfolio_runs
    op.create_table(
        "portfolio_runs",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column(
            "portfolio_id",
            sa.BigInteger,
            sa.ForeignKey(
                "portfolios.id",
                ondelete="SET NULL",
                name="fk_portfolio_runs_portfolio_id_portfolios",
            ),
        ),
        sa.Column(
            "user_id",
            sa.BigInteger,
            sa.ForeignKey(
                "users.id", ondelete="SET NULL", name="fk_portfolio_runs_user_id_users"
            ),
            nullable=False,
        ),
        sa.Column("run_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("method", sa.String(16), nullable=False),
        sa.Column("risk_free_rate", sa.Numeric(10, 6), nullable=False),
        sa.Column("min_stock_sd", sa.Numeric(10, 6)),
        sa.Column(
            "allow_shorting", sa.Boolean, nullable=False, server_default=sa.false()
        ),
        sa.Column("expected_return", sa.Numeric(12, 6)),
        sa.Column("volatility", sa.Numeric(12, 6)),
        sa.Column("sharpe", sa.Numeric(12, 6)),
        sa.Column("var_95", sa.Numeric(12, 6)),
        sa.Column("weights", JSONB),
        sa.Column("inputs_snapshot", JSONB),
        sa.Column("success", sa.Boolean, nullable=False),
        sa.Column("solver_message", sa.Text),
        sa.CheckConstraint(
            "method IN ('slsqp','qp')", name="ck_portfolio_runs_method_enum"
        ),
    )
    op.create_index("ix_portfolio_runs_user_id", "portfolio_runs", ["user_id"])
    op.create_index(
        "ix_portfolio_runs_user_time", "portfolio_runs", ["user_id", "run_at"]
    )

    # ----------------------------------------------------------- admin_config
    op.create_table(
        "admin_config",
        sa.Column("key", sa.String(64), primary_key=True),
        sa.Column("value", sa.Text, nullable=False),
        sa.Column("value_type", sa.String(16), nullable=False),
        sa.Column("description_ar", sa.Text),
        sa.Column("description_en", sa.Text),
        sa.Column(
            "updated_by",
            sa.BigInteger,
            sa.ForeignKey(
                "users.id", ondelete="SET NULL", name="fk_admin_config_updated_by_users"
            ),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "value_type IN ('number','string','bool','json')",
            name="ck_admin_config_value_type_enum",
        ),
    )

    # -------------------------------------------------------------- ui_labels
    op.create_table(
        "ui_labels",
        sa.Column("key", sa.String(128), primary_key=True),
        sa.Column("label_ar", sa.Text, nullable=False),
        sa.Column("label_en", sa.Text, nullable=False),
        sa.Column("description_ar", sa.Text),
        sa.Column("description_en", sa.Text),
        sa.Column("context", sa.String(64)),
        sa.Column(
            "updated_by",
            sa.BigInteger,
            sa.ForeignKey(
                "users.id", ondelete="SET NULL", name="fk_ui_labels_updated_by_users"
            ),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_ui_labels_context", "ui_labels", ["context"])

    # ------------------------------------------------------------ audit_log
    op.create_table(
        "audit_log",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column(
            "user_id",
            sa.BigInteger,
            sa.ForeignKey(
                "users.id", ondelete="SET NULL", name="fk_audit_log_user_id_users"
            ),
        ),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("resource_type", sa.String(64)),
        sa.Column("resource_id", sa.String(128)),
        sa.Column("ip_address", INET),
        sa.Column("user_agent", sa.String(512)),
        sa.Column("request_method", sa.String(8)),
        sa.Column("request_path", sa.String(512)),
        sa.Column("response_status", sa.Integer),
        sa.Column("details", JSONB),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_audit_log_user_id", "audit_log", ["user_id"])
    op.create_index("ix_audit_log_action_time", "audit_log", ["action", "created_at"])
    op.create_index("ix_audit_log_user_time", "audit_log", ["user_id", "created_at"])


def downgrade() -> None:
    # Drop in reverse dependency order so FKs don't block us.
    op.drop_table("audit_log")
    op.drop_table("ui_labels")
    op.drop_table("admin_config")
    op.drop_table("portfolio_runs")
    op.drop_table("portfolio_holdings")
    op.drop_table("portfolios")
    op.drop_table("sector_index_daily")
    op.drop_table("prices_daily")
    op.drop_table("stocks")
    op.drop_table("sectors")
    op.drop_table("user_disclaimer_acceptances")
    op.drop_table("disclaimer_versions")
    op.drop_table("subscriptions")
    op.drop_table("users")
