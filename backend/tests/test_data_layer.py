"""
Data Layer integration tests — uses SQLite in-memory (no PostgreSQL needed).

These tests verify the full flow from DB schema → seed → query without
requiring a running PostgreSQL instance (suitable for CI/CD).

PostgreSQL-specific types (JSONB, INET) are monkey-patched to SQLite-
compatible types so the full ORM model can be tested.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

import numpy as np
import pytest
from sqlalchemy import create_engine, select, func, String, Text, event
from sqlalchemy.orm import Session, sessionmaker

# Monkey-patch PostgreSQL dialect types for SQLite compatibility
# Must be done BEFORE importing models
from sqlalchemy.dialects.postgresql import INET, JSONB
import sqlalchemy.types as sa_types

# Register INET as String and JSONB as Text for SQLite
_original_inet_compile = INET.compile

# Use events to adapt types at DDL time for SQLite
from sqlalchemy import TypeDecorator
import json


class _SQLiteINET(TypeDecorator):
    impl = String(45)
    cache_ok = True


class _SQLiteJSONB(TypeDecorator):
    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is not None:
            return json.dumps(value)
        return None

    def process_result_value(self, value, dialect):
        if value is not None:
            return json.loads(value)
        return None


# Patch the type map for SQLite
from sqlalchemy.dialects import sqlite as sqlite_dialect  # noqa: E402

if not hasattr(sqlite_dialect, '_patched_for_pg_types'):
    # Register overrides
    from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
    _orig_process = SQLiteTypeCompiler.process

    def _patched_process(self, type_, **kw):
        if isinstance(type_, INET):
            return "VARCHAR(45)"
        if isinstance(type_, JSONB):
            return "TEXT"
        return _orig_process(self, type_, **kw)

    SQLiteTypeCompiler.process = _patched_process
    sqlite_dialect._patched_for_pg_types = True  # type: ignore[attr-defined]


from app.db.base import Base
from app.db.models import (
    Sector,
    Stock,
    SectorIndexDaily,
    PriceDaily,
    AdminConfig,
    User,
    Portfolio,
    PortfolioHolding,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def engine():
    """Create an in-memory SQLite engine with all tables.

    Registers PostgreSQL-specific functions (char_length) and adapts
    BigInteger PKs to SQLite-compatible INTEGER.
    """
    eng = create_engine("sqlite:///:memory:", echo=False)

    # Register char_length (PostgreSQL built-in) for SQLite
    @event.listens_for(eng, "connect")
    def _register_functions(dbapi_conn, connection_record):
        dbapi_conn.create_function("char_length", 1, lambda s: len(s) if s else 0)

    # Adapt BigInteger → Integer for SQLite so autoincrement works
    from sqlalchemy import BigInteger, Integer
    from sqlalchemy.schema import CreateTable

    @event.listens_for(Base.metadata, "before_create")
    def _adapt_bigint(target, connection, **kw):
        if connection.dialect.name == "sqlite":
            for table in target.sorted_tables:
                for col in table.columns:
                    if isinstance(col.type, BigInteger) and col.primary_key:
                        col.type = Integer()

    Base.metadata.create_all(eng)
    return eng


@pytest.fixture(scope="module")
def session_factory(engine):
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)


@pytest.fixture
def db(session_factory):
    """Yield a session that rolls back after each test."""
    session = session_factory()
    yield session
    session.rollback()
    session.close()


# ---------------------------------------------------------------------------
# Seed helpers
# ---------------------------------------------------------------------------
def _seed_sectors(db: Session) -> list[Sector]:
    sectors = [
        Sector(sector_code="TASI", name_ar="المؤشر العام", name_en="TASI"),
        Sector(sector_code="TBNI", name_ar="قطاع البنوك", name_en="Banks"),
        Sector(sector_code="TENI", name_ar="قطاع الطاقة", name_en="Energy"),
    ]
    db.add_all(sectors)
    db.flush()
    return sectors


def _seed_stocks(db: Session, sectors: list[Sector]) -> list[Stock]:
    bank_sector = next(s for s in sectors if s.sector_code == "TBNI")
    energy_sector = next(s for s in sectors if s.sector_code == "TENI")

    stocks = [
        Stock(
            symbol="1120", ticker_suffix="1120.SR",
            name_ar="الراجحي", name_en="Al Rajhi Bank",
            industry_ar="بنوك", industry_en="Banks",
            sector_id=bank_sector.id, is_active=True,
        ),
        Stock(
            symbol="2222", ticker_suffix="2222.SR",
            name_ar="أرامكو", name_en="Saudi Aramco",
            industry_ar="طاقة", industry_en="Energy",
            sector_id=energy_sector.id, is_active=True,
        ),
        Stock(
            symbol="7010", ticker_suffix="7010.SR",
            name_ar="STC", name_en="STC Group",
            industry_ar="اتصالات", industry_en="Telecom",
            sector_id=bank_sector.id, is_active=True,
        ),
        Stock(
            symbol="2010", ticker_suffix="2010.SR",
            name_ar="سابك", name_en="SABIC",
            industry_ar="مواد", industry_en="Materials",
            sector_id=energy_sector.id, is_active=True,
        ),
        Stock(
            symbol="1010", ticker_suffix="1010.SR",
            name_ar="الرياض", name_en="Riyad Bank",
            industry_ar="بنوك", industry_en="Banks",
            sector_id=bank_sector.id, is_active=True,
        ),
    ]
    db.add_all(stocks)
    db.flush()
    return stocks


def _seed_sector_index(db: Session, tasi_sector: Sector, n_days: int = 120) -> None:
    """Seed synthetic TASI index data for testing."""
    base_date = date(2025, 1, 1)
    base_price = 12000.0
    rng = np.random.default_rng(42)

    for i in range(n_days):
        trade_date = date.fromordinal(base_date.toordinal() + i)
        # Random walk
        base_price *= (1 + rng.normal(0.0002, 0.01))
        db.add(SectorIndexDaily(
            sector_id=tasi_sector.id,
            trade_date=trade_date,
            close=Decimal(str(round(base_price, 4))),
        ))
    db.flush()


def _seed_prices(db: Session, stocks: list[Stock], n_days: int = 120) -> None:
    """Seed synthetic daily prices for testing."""
    base_date = date(2025, 1, 1)
    rng = np.random.default_rng(42)

    for stock in stocks:
        price = 50.0 + rng.uniform(-20, 50)
        for i in range(n_days):
            trade_date = date.fromordinal(base_date.toordinal() + i)
            change = rng.normal(0.0003, 0.015)
            price *= (1 + change)
            db.add(PriceDaily(
                stock_id=stock.id,
                trade_date=trade_date,
                open=Decimal(str(round(price * 0.998, 4))),
                high=Decimal(str(round(price * 1.01, 4))),
                low=Decimal(str(round(price * 0.99, 4))),
                close=Decimal(str(round(price, 4))),
                adj_close=Decimal(str(round(price, 4))),
                volume=int(rng.integers(100000, 5000000)),
            ))
    db.flush()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
class TestSectorStockRelationship:
    def test_sectors_created(self, db):
        sectors = _seed_sectors(db)
        assert len(sectors) == 3
        count = db.execute(select(func.count()).select_from(Sector)).scalar()
        assert count == 3

    def test_stocks_linked_to_sectors(self, db):
        sectors = _seed_sectors(db)
        stocks = _seed_stocks(db, sectors)
        assert len(stocks) == 5

        # Query stocks by sector
        bank_stocks = db.execute(
            select(Stock)
            .join(Sector)
            .where(Sector.sector_code == "TBNI")
        ).scalars().all()
        assert len(bank_stocks) == 3  # AlRajhi, STC, Riyad

    def test_query_by_ticker(self, db):
        sectors = _seed_sectors(db)
        _seed_stocks(db, sectors)

        stock = db.execute(
            select(Stock).where(Stock.ticker_suffix == "2222.SR")
        ).scalar_one()
        assert stock.name_en == "Saudi Aramco"
        assert stock.name_ar == "أرامكو"

    def test_bilingual_names_not_null(self, db):
        sectors = _seed_sectors(db)
        _seed_stocks(db, sectors)

        null_count = db.execute(
            select(func.count())
            .where((Stock.name_ar.is_(None)) | (Stock.name_en.is_(None)))
        ).scalar()
        assert null_count == 0


class TestSectorIndexHistory:
    def test_index_data_seeded(self, db):
        sectors = _seed_sectors(db)
        tasi = next(s for s in sectors if s.sector_code == "TASI")
        _seed_sector_index(db, tasi, n_days=120)

        count = db.execute(
            select(func.count()).where(SectorIndexDaily.sector_id == tasi.id)
        ).scalar()
        assert count == 120

    def test_date_range(self, db):
        sectors = _seed_sectors(db)
        tasi = next(s for s in sectors if s.sector_code == "TASI")
        _seed_sector_index(db, tasi, n_days=60)

        min_date = db.execute(
            select(func.min(SectorIndexDaily.trade_date))
            .where(SectorIndexDaily.sector_id == tasi.id)
        ).scalar()
        max_date = db.execute(
            select(func.max(SectorIndexDaily.trade_date))
            .where(SectorIndexDaily.sector_id == tasi.id)
        ).scalar()

        assert min_date == date(2025, 1, 1)
        assert (max_date - min_date).days == 59


class TestPricesDaily:
    def test_prices_seeded(self, db):
        sectors = _seed_sectors(db)
        stocks = _seed_stocks(db, sectors)
        _seed_prices(db, stocks, n_days=60)

        count = db.execute(select(func.count()).select_from(PriceDaily)).scalar()
        assert count == 5 * 60  # 5 stocks × 60 days

    def test_price_per_stock(self, db):
        sectors = _seed_sectors(db)
        stocks = _seed_stocks(db, sectors)
        _seed_prices(db, stocks, n_days=30)

        for stock in stocks:
            count = db.execute(
                select(func.count()).where(PriceDaily.stock_id == stock.id)
            ).scalar()
            assert count == 30

    def test_price_values_positive(self, db):
        sectors = _seed_sectors(db)
        stocks = _seed_stocks(db, sectors)
        _seed_prices(db, stocks, n_days=10)

        min_close = db.execute(
            select(func.min(PriceDaily.close))
        ).scalar()
        assert float(min_close) > 0


class TestReturnsComputation:
    """Test that we can compute returns from seeded price data."""

    def test_log_returns_from_prices(self, db):
        sectors = _seed_sectors(db)
        stocks = _seed_stocks(db, sectors)
        _seed_prices(db, stocks, n_days=60)

        # Fetch prices for one stock
        prices = db.execute(
            select(PriceDaily.trade_date, PriceDaily.close)
            .where(PriceDaily.stock_id == stocks[0].id)
            .order_by(PriceDaily.trade_date)
        ).all()

        closes = np.array([float(p.close) for p in prices])
        log_returns = np.log(closes[1:] / closes[:-1])

        assert len(log_returns) == 59
        assert np.all(np.isfinite(log_returns))
        # Returns should be small daily values
        assert np.abs(log_returns).max() < 0.5

    def test_covariance_from_prices(self, db):
        sectors = _seed_sectors(db)
        stocks = _seed_stocks(db, sectors)
        _seed_prices(db, stocks, n_days=60)

        # Build returns matrix
        all_returns = []
        for stock in stocks:
            prices = db.execute(
                select(PriceDaily.close)
                .where(PriceDaily.stock_id == stock.id)
                .order_by(PriceDaily.trade_date)
            ).scalars().all()
            closes = np.array([float(p) for p in prices])
            log_ret = np.log(closes[1:] / closes[:-1])
            all_returns.append(log_ret)

        returns_matrix = np.column_stack(all_returns)
        assert returns_matrix.shape == (59, 5)

        # Covariance (ddof=0, Excel parity)
        cov = np.cov(returns_matrix, rowvar=False, ddof=0)
        assert cov.shape == (5, 5)
        assert np.all(np.linalg.eigvalsh(cov) >= -1e-10)  # PSD


class TestStockAnalyticsColumns:
    """Test that analytics columns can be updated."""

    def test_update_analytics(self, db):
        sectors = _seed_sectors(db)
        stocks = _seed_stocks(db, sectors)

        stock = stocks[0]
        stock.beta = Decimal("0.85")
        stock.capm_expected_return = Decimal("0.0925")
        stock.annual_volatility = Decimal("0.1243")
        stock.sharp_ratio = Decimal("0.32")
        stock.var_95_daily = Decimal("0.0215")
        stock.risk_ranking = "Moderately Conservative"
        stock.last_analytics_refresh = datetime.now(timezone.utc)
        db.flush()

        refreshed = db.get(Stock, stock.id)
        assert float(refreshed.beta) == pytest.approx(0.85)
        assert refreshed.risk_ranking == "Moderately Conservative"
