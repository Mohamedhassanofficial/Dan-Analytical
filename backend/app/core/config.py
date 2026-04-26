"""
Application configuration — loaded from environment with .env fallback.

All settings land here so every module imports from one place. Database URL,
SAMA risk-free rate default, data refresh window, CORS origins, etc.

Usage:
    from app.core.config import settings
    settings.database_url
"""
from __future__ import annotations

from typing import Annotated

from pydantic import Field, PostgresDsn, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Application ---
    app_name: str = "Tadawul Portfolio Optimizer"
    app_env: str = Field("development", description="development | staging | production")
    debug: bool = False

    # --- Database ---
    database_url: PostgresDsn = Field(
        default="postgresql+psycopg2://postgres:postgres@localhost:5432/tadawul",
        description="Primary sync DB URL (Alembic + most endpoints)",
    )
    database_url_async: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/tadawul",
        description="Async DB URL (hot-path endpoints; mirror database_url)",
    )
    db_pool_size: int = 10
    db_max_overflow: int = 20
    db_pool_pre_ping: bool = True

    # --- CORS (frontend dev servers) ---
    # NoDecode tells pydantic-settings NOT to JSON-decode the env var; the
    # _split_origins validator below parses the comma-separated string. Without
    # this, Render's `CORS_ORIGINS=https://...` raw URL trips json.loads and the
    # whole Settings() construction fails at import time.
    cors_origins: Annotated[list[str], NoDecode] = [
        "http://localhost:3000",
        "http://localhost:5173",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
    ]

    # --- Financial defaults (overridable via admin_config table) ---
    default_risk_free_rate: float = Field(
        0.0475, description="SAMA 12M SAIBOR fallback; admin_config.risk_free_rate overrides"
    )
    default_lookback_days: int = Field(
        252 * 5, description="~5 years of trading days for covariance estimation"
    )
    trading_days_per_year: int = 252

    # --- Market data refresh ---
    yfinance_refresh_hour_utc: int = Field(
        20, ge=0, le=23,
        description="Daily refresh hour (UTC). Tadawul closes 13:00 UTC; 20 UTC is safe.",
    )
    yfinance_max_retries: int = 3
    yfinance_request_timeout_sec: int = 30

    # --- Security (Phase B, seeded here so config is stable) ---
    secret_key: str = Field(
        "change-me-in-production-this-must-be-at-least-32-chars-long",
        min_length=32,
    )
    access_token_ttl_min: int = 30
    bcrypt_rounds: int = 12

    # --- Payment (Phase B) ---
    payment_gateway: str = Field("stcpay", pattern="^(stcpay|paytabs|disabled)$")
    subscription_price_sar: float = 199.0
    subscription_duration_days: int = 30

    # --- Compliance / audit ---
    audit_log_retention_days: int = 365 * 2  # PDPL baseline retention
    pdpl_data_region: str = Field("KSA", description="Must be a Saudi region per PDPL")

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, v):
        if isinstance(v, str):
            return [o.strip() for o in v.split(",") if o.strip()]
        return v

    @field_validator("database_url", mode="before")
    @classmethod
    def _normalise_sync_url(cls, v):
        # Render's managed Postgres exposes DATABASE_URL as `postgres://…`. Pydantic's
        # PostgresDsn needs the explicit driver, so swap to psycopg2 here.
        if isinstance(v, str) and v.startswith("postgres://"):
            return "postgresql+psycopg2://" + v[len("postgres://"):]
        if isinstance(v, str) and v.startswith("postgresql://"):
            return "postgresql+psycopg2://" + v[len("postgresql://"):]
        return v

    @model_validator(mode="after")
    def _derive_async_url(self):
        # If only DATABASE_URL is set (Render's default), build the async one
        # from it by swapping the driver. Local dev still wins via .env override.
        sync_str = str(self.database_url)
        default_async = "postgresql+asyncpg://postgres:postgres@localhost:5432/tadawul"
        if self.database_url_async == default_async and sync_str.startswith("postgresql+psycopg2://"):
            self.database_url_async = sync_str.replace(
                "postgresql+psycopg2://", "postgresql+asyncpg://", 1,
            )
        return self


settings = Settings()
