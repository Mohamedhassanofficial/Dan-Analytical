# Tadawul Portfolio Optimizer — Frontend

Bilingual React + TypeScript + Vite + Tailwind app that talks to the FastAPI
backend at `../backend`. Auth, subscription, disclaimer gating, optimization
workflow, run history, admin panel.

## Layout

```
frontend/
├── index.html
├── package.json
├── tsconfig.json
├── vite.config.ts
├── tailwind.config.js
├── postcss.config.js
├── .env.example
├── public/
│   └── favicon.svg
└── src/
    ├── main.tsx         # app entry, providers
    ├── App.tsx          # routes
    ├── index.css        # Tailwind base + component classes
    ├── i18n/            # ar.json, en.json, init
    ├── api/             # typed fetch wrappers (auth, portfolio, payments, admin)
    ├── contexts/        # AuthContext, LocaleContext
    ├── components/      # Layout, Sidebar, TopBar, ProtectedRoute, AuthShell, LanguageSwitch
    ├── pages/           # Login, Register, Disclaimer, Subscribe, Dashboard, Optimize, History, PortfolioList, PaymentReturn
    │   └── admin/       # Config, Upload
    └── lib/             # tokens, format helpers
```

## Setup

```bash
cd frontend
cp .env.example .env        # usually fine unchanged — Vite proxy handles /api/v1
npm install
npm run dev
# → http://localhost:5173 (proxies /api/* to http://localhost:8000)
```

## Scripts

```bash
npm run dev        # Vite dev server with HMR
npm run build      # typecheck + production bundle in dist/
npm run preview    # serve dist/ on port 5173
npm run typecheck  # `tsc --noEmit`
npm run lint       # ESLint (TypeScript + React Hooks + Refresh)
```

## Navigation flow

1. `/register` → `/disclaimer` → `/subscribe` → dashboard at `/`
2. `/login` → dashboard at `/` (redirects to `/disclaimer` or `/subscribe` if user hasn't completed either)
3. Admins see extra `/admin/config` and `/admin/upload` links in the sidebar

## Bilingual (AR / EN)

- `LocaleProvider` tracks current locale in `localStorage` and updates
  `document.dir` + `document.lang`.
- All user-facing strings live in `src/i18n/ar.json` / `en.json` — use
  `t("key")` via `react-i18next`.
- When adding a new UI string, add it to BOTH files. There is no fallback —
  missing Arabic text ships as English and vice versa.

## API client

- `src/api/client.ts` — central `fetch` wrapper
  - Injects `Authorization: Bearer <access>` from `tokens.ts`
  - On 401 automatically refreshes using the refresh token and retries once
  - Deduplicates concurrent refresh attempts (only one network call flies)
  - Surfaces errors as `ApiError` — `if (e instanceof ApiError)` pattern

## Environment

Copy `.env.example` to `.env`. The one variable that matters is
`VITE_API_BASE_URL` — leave as `/api/v1` to use the Vite proxy in dev, or set
a full URL like `https://api.example.com/api/v1` for staging/production.

## Scope note

The full 149-screen UI from `Web-Design-Portfolio-Optimization-Requirments2.pptx`
is not yet implemented. Phase C currently ships the foundational ~15 screens:
auth flow, disclaimer gate, subscription, dashboard, optimizer, run history,
admin config and upload. Subsequent iterations add the remaining screens
(portfolio builder, correlation heatmap, VaR tracker, target-loss alerts, user
account settings, stock browser, labels editor, etc.) — see the plan at
`../.claude/plans/1-pdf-encapsulated-hare.md`.
