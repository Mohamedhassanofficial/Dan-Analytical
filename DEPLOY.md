# Render deployment walkthrough

This repo ships a `render.yaml` Blueprint that provisions the entire stack on
[Render](https://render.com) in one step:

| Resource     | Type        | Plan | What it runs                                |
|--------------|-------------|------|---------------------------------------------|
| `tadawul-db` | PostgreSQL  | Free | Managed Postgres (90-day free trial)        |
| `tadawul-api`| Web service | Free | FastAPI + uvicorn (via `backend/start.sh`)  |
| `tadawul-web`| Static site | Free | Vite-built React bundle in `frontend/dist`  |

> **Goal**: give Loay a public URL he can hit from KSA, sign in as the demo
> user, and click around without us recording videos. Free tier sleeps after
> 15 min of idle traffic — first request after sleep takes ~30 s.

---

## One-time setup

1. **Create a Render account** at https://dashboard.render.com (GitHub OAuth
   is fine).
2. **Click `New` → `Blueprint`**.
3. **Select this repo** (`Mohamedhassanofficial/Dan-Analytical`) and the
   `main` branch.
4. Render reads `render.yaml`, shows you the three resources it will create,
   and asks for the env vars marked `sync: false`. **Skip them on this
   first pass — Render will create the resources first; the URLs we need
   for those env vars only exist after the first deploy.**
5. Click **`Apply`**. Render provisions the database, then deploys the API
   and the frontend in parallel.

After the first deploy, both web services have their public URLs:

- API:  `https://tadawul-api.onrender.com`
- Web:  `https://tadawul-web.onrender.com`

(The exact subdomain depends on Render's auto-naming — check the dashboard.)

## Wire the two web services together

1. **Backend `CORS_ORIGINS`**:
   - Dashboard → `tadawul-api` → `Environment` → set `CORS_ORIGINS` to the
     web service URL, e.g. `https://tadawul-web.onrender.com`.
   - Save → Render redeploys the api.

2. **Frontend `VITE_API_BASE_URL`** (build-time):
   - Dashboard → `tadawul-web` → `Environment` → set `VITE_API_BASE_URL` to
     `https://tadawul-api.onrender.com/api/v1`.
   - Save → Render rebuilds the static bundle.

Both services should now be green. Test:

```bash
curl https://tadawul-api.onrender.com/health
# → {"status":"ok","service":"Tadawul Portfolio Optimizer","env":"production"}
```

## What happens on every deploy

`backend/start.sh` is the api service's start command. On every cold start it:

1. `alembic upgrade head` — applies any new migrations.
2. `python -m scripts.seed_all` — sectors, stocks, sector history,
   admin_config defaults, disclaimer, ui_labels (all idempotent — uses
   `on_conflict_do_nothing`).
3. `python -m scripts.seed_all_stocks_analytics` — fills the 14 indicator
   columns + disclosure dates for the 233 active stocks.
4. `python -m scripts.seed_demo_prices` — generates 756 days × 233 stocks of
   synthetic prices so the Markowitz solver has data to work with.
5. `uvicorn app.main:app --host 0.0.0.0 --port $PORT` — starts the API.

> **Skipping seeds**: set `SKIP_SEEDS=1` on the api service after Loay has
> made any admin edits, so subsequent deploys don't try to re-bootstrap.

## Demo credentials (no manual step needed)

`start.sh` runs `scripts/seed_demo_user.py` on every cold start. That
script creates (or refreshes) a fully-set-up demo user — admin role,
disclaimer accepted, active subscription — so Loay can sign in
straight away.

```
Email:     demo@tadawul.local
Password:  demo-video-2026
```

Override either via env vars on the api service if you want a different
identity (`DEMO_USER_EMAIL`, `DEMO_USER_PASSWORD`). The seed is
idempotent — re-running keeps the password/admin flag in sync without
duplicating the user.

When you send Loay the link, paste him these two:

```
https://tadawul-web.onrender.com/login
demo@tadawul.local  /  demo-video-2026
```

## Going beyond the free tier

When the 90-day free Postgres trial ends, Render will prompt to upgrade. The
cheapest paid Postgres plan is `Starter` at ~$7/month. The api and web
services can stay on Free until traffic grows.

If cold-start latency becomes a problem during a live demo, upgrade only the
api service to `Starter` ($7/month) — that disables the 15-min idle sleep.
