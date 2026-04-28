#!/usr/bin/env bash
# Tadawul API — Render start command.
#
# Block on schema + the seeds Loay needs for first-login (catalogue +
# demo user). Heavy analytics/price seeds run in the background after
# uvicorn binds to $PORT so Render's deploy timeout isn't tripped.
#
# Render's free tier uses a single web instance, so there is no race here.
set -euo pipefail

echo "── alembic upgrade head ──────────────────────────────────────────────"
alembic upgrade head || { echo "MIGRATION FAILED — aborting"; exit 1; }

if [[ "${SKIP_SEEDS:-0}" != "1" ]]; then
  echo "── seed_all (sectors, stocks, history, admin_config, labels) ───────"
  python -m scripts.seed_all || echo "seed_all reported a non-fatal error; continuing"

  echo "── seed_demo_user (idempotent admin demo@tadawul.local) ────────────"
  python -m scripts.seed_demo_user || echo "demo user seed skipped"

  # Analytics seed moved to FOREGROUND (was bg). With 269 stocks this finishes
  # in ~30s and guarantees the new IPOs (BURGERIZZR, JAHEZ, FLYNAS, etc.) have
  # populated analytics before uvicorn answers the first request — empty
  # cells for new stocks are no longer possible.
  echo "── seed_all_stocks_analytics (full universe synthetic indicators) ──"
  python -m scripts.seed_all_stocks_analytics || echo "analytics seed skipped"

  # The price seed stays in background — it inserts 756 × 269 ≈ 200k rows
  # which takes 3-5 minutes and would otherwise trip Render's deploy timeout.
  (
    sleep 5
    echo "── (bg) seed_demo_prices (756d × ~269 stocks for Markowitz) ─────"
    python -m scripts.seed_demo_prices || echo "prices seed skipped"

    echo "── (bg) price seed complete ──"
  ) &
fi

echo "── starting uvicorn on port ${PORT:-8000} ──────────────────────────"
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --workers 1
