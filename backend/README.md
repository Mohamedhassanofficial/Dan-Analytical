# Tadawul Portfolio Optimizer — Backend

Phase A deliverables: PostgreSQL schema, yfinance data pipeline, admin API,
Excel upload, audit logging. Built on FastAPI + SQLAlchemy 2.0 + Alembic.

## Layout

```
backend/
├── app/
│   ├── api/v1/         # FastAPI routers (admin, ...)
│   ├── core/           # config.py (pydantic-settings)
│   ├── db/             # Base, session, models
│   ├── schemas/        # Pydantic request/response
│   ├── services/       # market_data.py (yfinance refresher)
│   └── main.py         # FastAPI app entry
├── alembic/
│   ├── env.py
│   ├── script.py.mako
│   └── versions/
├── scripts/
│   ├── seed_stocks.py
│   ├── seed_sector_history.py
│   ├── seed_admin_config.py
│   ├── seed_all.py
│   └── refresh_prices.py
├── alembic.ini
└── .env.example
```

## Setup

```bash
# 1) Python env
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r ../requirements.txt -r ../requirements-dev.txt

# 2) PostgreSQL (local dev)
createdb tadawul                   # or: docker run -e POSTGRES_DB=tadawul -p 5432:5432 postgres:16

# 3) Environment
cp .env.example .env
# edit .env — at minimum set DATABASE_URL and SECRET_KEY

# 4) Migrate
alembic upgrade head

# 5) Seed (uses the xlsx/csv files at the repo root)
python -m scripts.seed_all

# 6) Run
uvicorn app.main:app --reload --port 8000
# → http://localhost:8000/docs
```

## Running the yfinance refresh

```bash
python -m scripts.refresh_prices          # today
python -m scripts.refresh_prices --as-of 2026-04-24
```

Schedule in production via cron (preferred) or APScheduler:

```cron
0 20 * * * cd /app/backend && /app/backend/.venv/bin/python -m scripts.refresh_prices
```

## Admin API (Phase A auth = shared secret)

All `/api/v1/admin/*` endpoints require header `X-Admin-Token: <SECRET_KEY>`.
This is temporary — Phase B replaces it with JWT + `users.is_admin`.

Key endpoints:

- `GET  /api/v1/admin/config` — list all configurable runtime settings
- `GET  /api/v1/admin/config/{key}` — fetch one
- `PUT  /api/v1/admin/config/{key}` — update value (audit-logged)
- `POST /api/v1/admin/upload/sector-history` — upload Excel/CSV of sector history
  (columns: `Sector Code`, `Date`, `Close`)
- `POST /api/v1/admin/refresh-prices` — trigger yfinance refresh synchronously

## Alembic cheatsheet

```bash
alembic upgrade head                                    # apply all migrations
alembic downgrade -1                                    # undo last
alembic revision --autogenerate -m "add column X"       # generate from model diff
alembic current                                         # show current revision
alembic history                                         # show full history
```

After editing `app/db/models.py`, re-run `alembic revision --autogenerate`
and review the generated migration before committing.

## Verification checklist (Phase A)

- [ ] `alembic upgrade head` creates 14 tables without errors
- [ ] `python -m scripts.seed_all` inserts 234 stocks + 44K sector-history rows
- [ ] `curl -H "X-Admin-Token: $SECRET_KEY" http://localhost:8000/api/v1/admin/config`
      returns the seeded defaults
- [ ] `python -m scripts.refresh_prices` pulls at least 1 day of yfinance data per active stock
- [ ] The audit log shows a `market_data.refresh` entry with accurate counts
