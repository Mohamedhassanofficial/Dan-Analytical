"""
ORM models for the Tadawul Portfolio Optimizer platform.

Alembic autogenerate reads `Base.metadata`, so every model defined here is
picked up automatically when running `alembic revision --autogenerate`.

Schema overview
---------------
Identity / auth (Phase B will add session tokens + disclaimer versioning):
    users, subscriptions, disclaimer_versions, user_disclaimer_acceptances

Market data:
    stocks, sectors, prices_daily, sector_index_daily

Portfolio workflow:
    portfolios, portfolio_holdings, portfolio_runs

Operations / compliance:
    admin_config, ui_labels, audit_log

Bilingual rule (see memory: feedback_bilingual): every label/description/name
that reaches a user has `_ar` AND `_en` columns. Never collapse to one.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, _now_utc


# ---------------------------------------------------------------------------
# IDENTITY
# ---------------------------------------------------------------------------
class User(Base, TimestampMixin):
    """
    End-user or admin. Registration fields required by the PDF brief:
    national ID, mobile, email, password. Names are bilingual because
    reports/PDFs must print them in the user's locale.
    """
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    national_id: Mapped[str] = mapped_column(String(10), unique=True, nullable=False)
    mobile: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)

    full_name_ar: Mapped[str | None] = mapped_column(String(255))
    full_name_en: Mapped[str | None] = mapped_column(String(255))
    preferred_locale: Mapped[str] = mapped_column(String(5), default="ar", nullable=False)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    disclaimer_accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_login_ip: Mapped[str | None] = mapped_column(INET)

    # Relationships
    portfolios: Mapped[list["Portfolio"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    subscriptions: Mapped[list["Subscription"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    portfolio_runs: Mapped[list["PortfolioRun"]] = relationship(back_populates="user")

    __table_args__ = (
        CheckConstraint("char_length(national_id) = 10", name="national_id_length"),
        CheckConstraint("preferred_locale IN ('ar', 'en')", name="preferred_locale_enum"),
    )


class Subscription(Base, TimestampMixin):
    """Paid subscription record. One user may have multiple (history)."""
    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    gateway: Mapped[str] = mapped_column(String(20), nullable=False)  # stcpay | paytabs
    gateway_transaction_id: Mapped[str | None] = mapped_column(String(128), unique=True)

    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="SAR", nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)  # pending|completed|failed|refunded

    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    raw_gateway_payload: Mapped[dict | None] = mapped_column(JSONB)

    user: Mapped[User] = relationship(back_populates="subscriptions")

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','completed','failed','refunded')",
            name="status_enum",
        ),
        CheckConstraint("gateway IN ('stcpay','paytabs')", name="gateway_enum"),
        Index("ix_subscriptions_user_expires", "user_id", "expires_at"),
    )


class DisclaimerVersion(Base, TimestampMixin):
    """Versioned disclaimer text. Users accept a specific version for audit."""
    __tablename__ = "disclaimer_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    version: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    body_ar: Mapped[str] = mapped_column(Text, nullable=False)
    body_en: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class UserDisclaimerAcceptance(Base):
    """Record that a user accepted a specific disclaimer version."""
    __tablename__ = "user_disclaimer_acceptances"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    disclaimer_id: Mapped[int] = mapped_column(
        ForeignKey("disclaimer_versions.id"), nullable=False
    )
    accepted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now_utc, nullable=False
    )
    ip_address: Mapped[str | None] = mapped_column(INET)

    __table_args__ = (
        UniqueConstraint("user_id", "disclaimer_id", name="user_disclaimer_unique"),
    )


# ---------------------------------------------------------------------------
# MARKET DATA
# ---------------------------------------------------------------------------
class Sector(Base, TimestampMixin):
    """Tadawul sector index (21 sectors in the 10-year feed)."""
    __tablename__ = "sectors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sector_code: Mapped[str] = mapped_column(String(10), unique=True, nullable=False)
    name_ar: Mapped[str] = mapped_column(String(255), nullable=False)
    name_en: Mapped[str] = mapped_column(String(255), nullable=False)
    description_ar: Mapped[str | None] = mapped_column(Text)
    description_en: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    stocks: Mapped[list["Stock"]] = relationship(back_populates="sector")
    index_history: Mapped[list["SectorIndexDaily"]] = relationship(
        back_populates="sector", cascade="all, delete-orphan"
    )


class Stock(Base, TimestampMixin):
    """
    Tadawul stock (234 symbols in the seed file). Mapped to sectors via
    the `Index Code` column in Stock-List-Arabic-and-English.xlsx.
    """
    __tablename__ = "stocks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(10), unique=True, nullable=False)
    ticker_suffix: Mapped[str] = mapped_column(String(12), unique=True, nullable=False)  # "2222.SR"

    name_ar: Mapped[str | None] = mapped_column(String(255))
    name_en: Mapped[str | None] = mapped_column(String(255))
    industry_ar: Mapped[str | None] = mapped_column(String(255))
    industry_en: Mapped[str | None] = mapped_column(String(255))

    sector_id: Mapped[int | None] = mapped_column(ForeignKey("sectors.id"), index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Pre-computed analytics (refreshed nightly; nullable = not yet computed).
    # Full set per PPTX slide 83 — 14 indicators in two groups (Risk / Financial).
    # Risk indicators:
    beta: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    capm_expected_return: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    daily_volatility: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    annual_volatility: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    sharp_ratio: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    var_95_daily: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    risk_ranking: Mapped[str | None] = mapped_column(String(40))
    # Financial indicators (from yfinance Ticker.info):
    pe_ratio: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    market_to_book: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    roe: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    fcf_yield: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    leverage_ratio: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    eps: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    dividend_yield: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    annual_dividend_rate: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    # Latest price snapshot (for the "last update" banner + reference).
    last_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    last_price_date: Mapped[date | None] = mapped_column(Date)
    last_analytics_refresh: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Fundamental disclosure dates (shown in the Screener's Financial Ratios
    # band — Loay slide). Patchy per issuer, so all nullable.
    last_balance_sheet_date: Mapped[date | None] = mapped_column(Date)
    last_income_statement_date: Mapped[date | None] = mapped_column(Date)
    latest_dividend_date: Mapped[date | None] = mapped_column(Date)

    sector: Mapped[Sector | None] = relationship(back_populates="stocks")
    prices: Mapped[list["PriceDaily"]] = relationship(
        back_populates="stock", cascade="all, delete-orphan"
    )


class PriceDaily(Base):
    """Daily OHLCV from yfinance. Partition by date range in production."""
    __tablename__ = "prices_daily"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    stock_id: Mapped[int] = mapped_column(
        ForeignKey("stocks.id", ondelete="CASCADE"), nullable=False
    )
    trade_date: Mapped[date] = mapped_column(Date, nullable=False)

    open: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    high: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    low: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    close: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    adj_close: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    volume: Mapped[int | None] = mapped_column(BigInteger)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now_utc, nullable=False
    )

    stock: Mapped[Stock] = relationship(back_populates="prices")

    __table_args__ = (
        UniqueConstraint("stock_id", "trade_date", name="stock_date_unique"),
        Index("ix_prices_daily_stock_date", "stock_id", "trade_date"),
        Index("ix_prices_daily_date", "trade_date"),
    )


class SectorIndexDaily(Base):
    """Daily sector index closing value."""
    __tablename__ = "sector_index_daily"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    sector_id: Mapped[int] = mapped_column(
        ForeignKey("sectors.id", ondelete="CASCADE"), nullable=False
    )
    trade_date: Mapped[date] = mapped_column(Date, nullable=False)
    close: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)

    sector: Mapped[Sector] = relationship(back_populates="index_history")

    __table_args__ = (
        UniqueConstraint("sector_id", "trade_date", name="sector_date_unique"),
        Index("ix_sector_index_daily_sector_date", "sector_id", "trade_date"),
    )


# ---------------------------------------------------------------------------
# PORTFOLIO WORKFLOW
# ---------------------------------------------------------------------------
class Portfolio(Base, TimestampMixin):
    """Named portfolio owned by a user. Composed of PortfolioHolding rows."""
    __tablename__ = "portfolios"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)

    initial_capital: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    target_loss_threshold: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 6),
        comment="Decimal fraction. Alert fires when portfolio loss exceeds this.",
    )

    user: Mapped[User] = relationship(back_populates="portfolios")
    holdings: Mapped[list["PortfolioHolding"]] = relationship(
        back_populates="portfolio", cascade="all, delete-orphan"
    )
    runs: Mapped[list["PortfolioRun"]] = relationship(
        back_populates="portfolio", cascade="all, delete-orphan"
    )


class PortfolioHolding(Base, TimestampMixin):
    """Individual stock allocation within a portfolio."""
    __tablename__ = "portfolio_holdings"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    portfolio_id: Mapped[int] = mapped_column(
        ForeignKey("portfolios.id", ondelete="CASCADE"), nullable=False
    )
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"), nullable=False)

    weight: Mapped[Decimal] = mapped_column(Numeric(10, 6), nullable=False)
    shares: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))

    portfolio: Mapped[Portfolio] = relationship(back_populates="holdings")
    stock: Mapped[Stock] = relationship()

    __table_args__ = (
        UniqueConstraint("portfolio_id", "stock_id", name="portfolio_stock_unique"),
        CheckConstraint("weight >= 0 AND weight <= 1", name="weight_bounds"),
    )


class PortfolioRun(Base):
    """
    Audit-grade snapshot of an optimization run. Stores inputs + outputs so
    any result shown to the user can be reproduced exactly (required for
    SDAIA/PDPL accountability).
    """
    __tablename__ = "portfolio_runs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    portfolio_id: Mapped[int | None] = mapped_column(
        ForeignKey("portfolios.id", ondelete="SET NULL")
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=False, index=True
    )

    run_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now_utc, nullable=False
    )
    method: Mapped[str] = mapped_column(String(16), nullable=False)  # slsqp | qp

    risk_free_rate: Mapped[Decimal] = mapped_column(Numeric(10, 6), nullable=False)
    min_stock_sd: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    allow_shorting: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    expected_return: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))
    volatility: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))
    sharpe: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))
    var_95: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))

    weights: Mapped[dict | None] = mapped_column(JSONB)
    inputs_snapshot: Mapped[dict | None] = mapped_column(JSONB)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    solver_message: Mapped[str | None] = mapped_column(Text)

    portfolio: Mapped[Portfolio | None] = relationship(back_populates="runs")
    user: Mapped[User] = relationship(back_populates="portfolio_runs")

    __table_args__ = (
        CheckConstraint("method IN ('slsqp','qp')", name="method_enum"),
        Index("ix_portfolio_runs_user_time", "user_id", "run_at"),
    )


# ---------------------------------------------------------------------------
# OPERATIONS / COMPLIANCE
# ---------------------------------------------------------------------------
class AdminConfig(Base, TimestampMixin):
    """
    Key-value store for admin-editable runtime config per the PDF's admin
    dashboard requirements: risk-free rate, data loading time, lookback
    window, stock list refresh, etc. Also versioned in audit_log.
    """
    __tablename__ = "admin_config"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)   # JSON-encoded
    value_type: Mapped[str] = mapped_column(String(16), nullable=False)  # number|string|bool|json
    description_ar: Mapped[str | None] = mapped_column(Text)
    description_en: Mapped[str | None] = mapped_column(Text)
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))

    __table_args__ = (
        CheckConstraint(
            "value_type IN ('number','string','bool','json')", name="value_type_enum"
        ),
    )


class UiLabel(Base, TimestampMixin):
    """
    Admin-editable bilingual labels for the entire UI. The PDF requires
    admins to be able to update "all titles, labels, and field descriptions
    as displayed in charts and front-end screens." The frontend fetches
    these at boot and hydrates its i18n bundle.
    """
    __tablename__ = "ui_labels"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    label_ar: Mapped[str] = mapped_column(Text, nullable=False)
    label_en: Mapped[str] = mapped_column(Text, nullable=False)
    description_ar: Mapped[str | None] = mapped_column(Text)
    description_en: Mapped[str | None] = mapped_column(Text)
    context: Mapped[str | None] = mapped_column(String(64), index=True)  # dashboard|admin|auth|charts
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


class AuditLog(Base):
    """
    Append-only log of user and admin actions. Required by PDF §3 (Audit
    Logging) for SDAIA/PDPL compliance. Retained for `audit_log_retention_days`
    (default 2 years per PDPL).
    """
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    action: Mapped[str] = mapped_column(String(64), nullable=False)  # login|optimize|config_update|...
    resource_type: Mapped[str | None] = mapped_column(String(64))
    resource_id: Mapped[str | None] = mapped_column(String(128))

    ip_address: Mapped[str | None] = mapped_column(INET)
    user_agent: Mapped[str | None] = mapped_column(String(512))
    request_method: Mapped[str | None] = mapped_column(String(8))
    request_path: Mapped[str | None] = mapped_column(String(512))
    response_status: Mapped[int | None] = mapped_column(Integer)

    details: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now_utc, nullable=False
    )

    __table_args__ = (
        Index("ix_audit_log_action_time", "action", "created_at"),
        Index("ix_audit_log_user_time", "user_id", "created_at"),
    )


__all__ = [
    "User",
    "Subscription",
    "DisclaimerVersion",
    "UserDisclaimerAcceptance",
    "Sector",
    "Stock",
    "PriceDaily",
    "SectorIndexDaily",
    "Portfolio",
    "PortfolioHolding",
    "PortfolioRun",
    "AdminConfig",
    "UiLabel",
    "AuditLog",
]
