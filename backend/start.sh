#!/usr/bin/env bash
# Tadawul API — Render start command.
#
# Runs migrations and seeds idempotently on every cold start, then launches
# uvicorn. Seeds are safe to re-run (on_conflict_do_nothing for catalogue
# data; deterministic deletes for synthetic price/analytics rows).
#
# Render's free tier uses a single web instance, so there is no race here.
set -euo pipefail

echo "── alembic upgrade head ──────────────────────────────────────────────"
alembic upgrade head

if [[ "${SKIP_SEEDS:-0}" != "1" ]]; then
  echo "── seed_all (sectors, stocks, history, admin_config, labels) ───────"
  python -m scripts.seed_all || echo "seed_all reported a non-fatal error; continuing"

  echo "── seed_all_stocks_analytics (full universe synthetic indicators) ──"
  python -m scripts.seed_all_stocks_analytics || echo "analytics seed skipped"

  echo "── seed_demo_prices (756d × ~233 stocks for Markowitz) ─────────────"
  python -m scripts.seed_demo_prices || echo "prices seed skipped"

  echo "── seed_demo_user (idempotent admin demo@tadawul.local) ────────────"
  python -m scripts.seed_demo_user || echo "demo user seed skipped"
fi

echo "── starting uvicorn on port ${PORT:-8000} ──────────────────────────"
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --workers 1
