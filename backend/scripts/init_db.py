"""
One-command database bootstrap for the Tadawul Portfolio Optimizer.

This script:
  1. Verifies PostgreSQL is reachable
  2. Creates the `tadawul` database if it doesn't exist
  3. Runs Alembic migrations to HEAD
  4. Executes the full seed pipeline (sectors, stocks, sector history,
     admin config, disclaimer, UI labels, demo analytics)
  5. Prints a verification summary

Usage (from backend/):
    python -m scripts.init_db
    python -m scripts.init_db --skip-seed     # migrations only
    python -m scripts.init_db --reset         # DROP + CREATE (⚠️ destructive)
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import settings  # noqa: E402


# ---------------------------------------------------------------------------
# Database creation
# ---------------------------------------------------------------------------
def _parse_pg_url(url: str) -> dict:
    """Extract host, port, user, password, dbname from a SQLAlchemy PG URL."""
    # postgresql+psycopg2://user:pass@host:port/dbname
    from urllib.parse import urlparse
    parsed = urlparse(str(url))
    return {
        "host": parsed.hostname or "localhost",
        "port": parsed.port or 5432,
        "user": parsed.username or "postgres",
        "password": parsed.password or "postgres",
        "dbname": parsed.path.lstrip("/") or "tadawul",
    }


def ensure_database_exists(reset: bool = False) -> bool:
    """Connect to Postgres and create the database if missing. Returns True if created."""
    params = _parse_pg_url(settings.database_url)
    dbname = params.pop("dbname")

    try:
        # Connect to the default 'postgres' database to create ours
        conn = psycopg2.connect(dbname="postgres", **params)
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cur = conn.cursor()

        if reset:
            # Terminate existing connections before dropping
            cur.execute(f"""
                SELECT pg_terminate_backend(pid) FROM pg_stat_activity
                WHERE datname = %s AND pid <> pg_backend_pid()
            """, (dbname,))
            cur.execute(f'DROP DATABASE IF EXISTS "{dbname}"')
            print(f"⚠️  Dropped database '{dbname}'")

        cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (dbname,))
        exists = cur.fetchone() is not None

        if not exists:
            cur.execute(f'CREATE DATABASE "{dbname}" ENCODING \'UTF8\'')
            print(f"✅ Created database '{dbname}'")
            cur.close()
            conn.close()
            return True

        print(f"✅ Database '{dbname}' already exists")
        cur.close()
        conn.close()
        return False

    except psycopg2.OperationalError as exc:
        print(f"\n❌ Cannot connect to PostgreSQL: {exc}")
        print("\nMake sure PostgreSQL is running. Quick options:")
        print("  1. docker compose up -d          (uses docker-compose.yml)")
        print("  2. brew services start postgresql (macOS)")
        print("  3. sudo systemctl start postgresql (Linux)")
        print(f"\nExpected connection: {params['user']}@{params['host']}:{params['port']}")
        sys.exit(1)


# ---------------------------------------------------------------------------
# Alembic migrations
# ---------------------------------------------------------------------------
def run_alembic_upgrade() -> None:
    """Run 'alembic upgrade head' as a subprocess."""
    backend_dir = Path(__file__).resolve().parent.parent
    print("\n🔄 Running Alembic migrations...")
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=str(backend_dir),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"❌ Alembic upgrade failed:\n{result.stderr}")
        sys.exit(1)
    # Show migration output
    for line in result.stdout.strip().split("\n"):
        if line.strip():
            print(f"   {line}")
    print("✅ Alembic at HEAD")


# ---------------------------------------------------------------------------
# Seed pipeline
# ---------------------------------------------------------------------------
def run_seed_pipeline() -> None:
    """Execute the full seed sequence."""
    from app.db.session import SessionLocal
    from scripts.seed_admin_config import seed as seed_admin_config
    from scripts.seed_disclaimer import seed as seed_disclaimer
    from scripts.seed_sector_history import seed as seed_sector_history
    from scripts.seed_stocks import (
        DEFAULT_INDEX_FILE,
        DEFAULT_STOCK_FILE,
        seed_sectors,
        seed_stocks,
    )
    from scripts.seed_ui_labels import seed as seed_ui_labels

    print("\n🌱 Seeding data...")

    # Step 1: Sectors
    with SessionLocal() as db:
        n_sectors = seed_sectors(db, DEFAULT_INDEX_FILE)
    print(f"   [1/7] Sectors upserted:           {n_sectors}")

    # Step 2: Stocks
    with SessionLocal() as db:
        n_stocks = seed_stocks(db, DEFAULT_STOCK_FILE)
    print(f"   [2/7] Stocks upserted:            {n_stocks}")

    # Step 3: Sector index history (10 years)
    n_history = seed_sector_history(DEFAULT_INDEX_FILE)
    print(f"   [3/7] Sector index daily rows:     {n_history:,}")

    # Step 4: Admin config defaults
    n_cfg = seed_admin_config()
    print(f"   [4/7] Admin config defaults:       {n_cfg}")

    # Step 5: Disclaimer v1
    seed_disclaimer()
    print("   [5/7] Disclaimer v1 activated")

    # Step 6: UI labels
    n_labels = seed_ui_labels()
    print(f"   [6/7] UI labels seeded:            {n_labels}")

    # Step 7: Demo analytics for screener
    try:
        from scripts.seed_demo_analytics import seed as seed_demo_analytics
        n_demo = seed_demo_analytics()
        print(f"   [7/7] Demo analytics seeded:       {n_demo} stocks")
    except Exception as exc:
        print(f"   [7/7] Demo analytics skipped:      {exc}")


# ---------------------------------------------------------------------------
# Verification summary
# ---------------------------------------------------------------------------
def print_summary() -> None:
    """Query table counts for a quick health check."""
    from sqlalchemy import text
    from app.db.session import SessionLocal

    tables = [
        "sectors", "stocks", "sector_index_daily", "prices_daily",
        "admin_config", "ui_labels", "disclaimer_versions",
        "portfolios", "portfolio_runs", "audit_log",
    ]

    print("\n" + "=" * 56)
    print("📊 Data Summary")
    print("=" * 56)

    with SessionLocal() as db:
        for table in tables:
            try:
                count = db.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()
                status = "✅" if count > 0 else "⚠️"
                print(f"   {status} {table:<28s} {count:>8,} rows")
            except Exception:
                print(f"   ❌ {table:<28s} (table missing)")

    print("=" * 56)
    print("\n✅ Database initialized. Start the API:")
    print("   uvicorn app.main:app --reload --port 8000")
    print()


# ---------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser(description="Bootstrap the Tadawul database.")
    ap.add_argument("--skip-seed", action="store_true", help="Only run migrations, skip seeding.")
    ap.add_argument("--reset", action="store_true", help="⚠️ DROP and recreate the database.")
    args = ap.parse_args()

    print("=" * 56)
    print("🏗️  Tadawul Portfolio Optimizer — DB Bootstrap")
    print("=" * 56)

    ensure_database_exists(reset=args.reset)
    run_alembic_upgrade()

    if not args.skip_seed:
        run_seed_pipeline()

    print_summary()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
