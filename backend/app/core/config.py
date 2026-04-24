"""
Application configuration — loaded from environment with .env fallback.

All settings land here so every module imports from one place. Database URL,
SAMA risk-free rate default, data refresh window, CORS origins, etc.

Usage:
    from app.core.config import settings
    settings.database_url
"""
from __future__ import annotations

from pydantic import Field, PostgresDsn, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


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
    cors_origins: list[str] = [
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


settings = Settings()
