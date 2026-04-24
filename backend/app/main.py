"""
Tadawul Portfolio Optimizer — FastAPI application entry point.

Mounted routers:
  - /api/v1/auth      (register, login, refresh, me, disclaimer)
  - /api/v1/portfolio (optimize, frontier, metrics, save, history)
  - /api/v1/admin     (config CRUD, Excel upload, refresh trigger)
  - /api/v1/payments  (STCPay / PayTabs — Phase B2)

Run (from backend/):
    uvicorn app.main:app --reload --port 8000
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import admin as admin_router
from app.api.v1 import auth as auth_router
from app.api.v1 import labels as labels_router
from app.api.v1 import payments as payments_router
from app.api.v1 import portfolio as portfolio_router
from app.api.v1 import stocks as stocks_router
from app.core.config import settings

app = FastAPI(
    title=settings.app_name,
    description=(
        "Bilingual Markowitz / CAPM / VaR portfolio optimization platform for "
        "the Saudi Tadawul market. Implements slides 123-126 of the approved "
        "project specification."
    ),
    version="0.3.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

API_PREFIX = "/api/v1"

app.include_router(auth_router.router, prefix=API_PREFIX)
app.include_router(labels_router.router, prefix=API_PREFIX)
app.include_router(stocks_router.router, prefix=API_PREFIX)
app.include_router(portfolio_router.router, prefix=API_PREFIX)
app.include_router(payments_router.router, prefix=API_PREFIX)
app.include_router(admin_router.router, prefix=API_PREFIX)


@app.get("/health", tags=["health"])
def health() -> dict:
    return {
        "status": "ok",
        "service": settings.app_name,
        "env": settings.app_env,
    }
