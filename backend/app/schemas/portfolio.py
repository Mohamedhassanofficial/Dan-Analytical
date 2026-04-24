"""Pydantic schemas for the portfolio optimization API."""
from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Shared inputs — either DB-backed (just tickers) or manual (full matrices)
# ---------------------------------------------------------------------------
class OptimizeRequest(BaseModel):
    tickers: list[str] = Field(..., min_length=2, max_length=100)

    # Option A: DB-backed — leave returns/cov/rf empty and set use_db_data
    use_db_data: bool = Field(
        True,
        description=(
            "If true, the server fetches prices + computes CAPM/covariance from "
            "the DB. If false, you must provide daily_returns or cov_daily below."
        ),
    )
    lookback_days: int | None = Field(
        None, ge=30, le=10 * 252, description="Override admin_config.lookback_days."
    )
    as_of: date | None = Field(
        None,
        description="Treat this date as 'today' for analytics (for back-testing).",
    )

    # Option B: manual inputs (legacy parity with root-level API)
    expected_returns: list[float] | None = None
    cov_daily: list[list[float]] | None = None
    daily_returns: list[list[float]] | None = None
    risk_free_rate: float | None = Field(
        None, ge=0, le=0.5,
        description="Override admin_config.risk_free_rate.",
    )

    # Solver / constraint controls
    method: Literal["slsqp", "qp"] = "qp"
    min_stock_sd: float | None = Field(
        None,
        description="Constraint cap σ_p ≤ this. Default = MIN of per-stock annualized SDs.",
    )
    apply_min_sd_constraint: bool = True
    apply_return_floor: bool = True
    allow_shorting: bool = False

    @field_validator("tickers")
    @classmethod
    def _unique(cls, v: list[str]) -> list[str]:
        seen: set[str] = set()
        out = []
        for t in v:
            t2 = t.strip()
            if t2 in seen:
                continue
            seen.add(t2)
            out.append(t2)
        return out


class OptimizeResponse(BaseModel):
    success: bool
    method: str
    message: str
    weights: dict[str, float]
    sharpe: float
    expected_return: float
    volatility: float
    sum_weights: float

    # Echo back the inputs the server used so the frontend can display them
    risk_free_rate: float
    min_stock_sd: float | None
    tickers: list[str]
    capm_expected_return: dict[str, float]
    annual_volatility: dict[str, float]
    beta: dict[str, float]
    cov_daily: list[list[float]] | None = None
    run_id: int | None = None


class FrontierPoint(BaseModel):
    target_return: float
    volatility: float
    weights: list[float]


class FrontierResponse(BaseModel):
    tickers: list[str]
    points: list[FrontierPoint]
    tangency_return: float
    tangency_volatility: float
    tangency_weights: dict[str, float]


class MetricsRequest(BaseModel):
    """For the live slider — recompute on a user-supplied weight vector."""
    tickers: list[str]
    weights: list[float]
    expected_returns: list[float] | None = None
    cov_daily: list[list[float]] | None = None
    daily_returns: list[list[float]] | None = None
    risk_free_rate: float | None = None
    use_db_data: bool = True


class MetricsResponse(BaseModel):
    sharpe: float
    expected_return: float
    volatility: float
    sum_weights: float
    risk_contribution: dict[str, float]
    var_95_daily: float
    var_95_10d: float
    cvar_95_daily: float


# ---------------------------------------------------------------------------
# Saved-portfolio CRUD
# ---------------------------------------------------------------------------
class HoldingIn(BaseModel):
    ticker: str
    weight: float = Field(..., ge=0, le=1)


class SavePortfolio(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    initial_capital: float | None = None
    target_loss_threshold: float | None = Field(None, ge=0, le=1)
    holdings: list[HoldingIn] = Field(..., min_length=1)


class PortfolioOut(BaseModel):
    id: int
    name: str
    description: str | None
    initial_capital: float | None
    target_loss_threshold: float | None
    holdings: list[HoldingIn]
    created_at: datetime
    updated_at: datetime


class PortfolioRunOut(BaseModel):
    id: int
    run_at: datetime
    method: str
    risk_free_rate: float
    expected_return: float | None
    volatility: float | None
    sharpe: float | None
    var_95: float | None
    success: bool
    weights: dict[str, float] | None
