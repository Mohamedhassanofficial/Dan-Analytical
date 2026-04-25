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
    initial_capital: float | None = Field(None, ge=0)
    target_loss_threshold: float | None = Field(None, ge=0, le=1)
    # holdings is optional: Loay's "create new portfolio" modal submits just
    # name + amount. The optimize flow still submits a full holdings list with
    # weights summing to 1 — both cases handled by the /portfolio/ POST.
    holdings: list[HoldingIn] = Field(default_factory=list, max_length=269)


class UpdatePortfolioRequest(BaseModel):
    """PATCH body: every field optional; omitted fields are left untouched."""
    name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = None
    initial_capital: float | None = Field(None, ge=0)
    target_loss_threshold: float | None = Field(None, ge=0, le=1)


class AddHoldingRequest(BaseModel):
    """Add one stock to a portfolio's holdings (no weight — set via compute)."""
    ticker: str = Field(..., min_length=1, max_length=12)


class ComputeWeightsRequest(BaseModel):
    """Trigger Markowitz optimization on a portfolio's existing holdings."""
    method: Literal["slsqp", "qp"] = "qp"
    risk_free_rate: float | None = Field(None, ge=0, le=0.5)
    lookback_days: int | None = Field(None, ge=30, le=10 * 252)
    apply_min_sd_constraint: bool = True
    apply_return_floor: bool = True
    allow_shorting: bool = False


class ComputeWeightsResponse(BaseModel):
    """Return from POST /portfolio/{id}/compute — mirrors OptimizeResponse but
    tied to the portfolio (weights have been persisted into its holdings)."""
    portfolio_id: int
    run_id: int
    success: bool
    method: str
    message: str
    sharpe: float
    expected_return: float
    volatility: float
    risk_free_rate: float
    weights: dict[str, float]
    annual_volatility: dict[str, float]
    beta: dict[str, float]
    capm_expected_return: dict[str, float]


class PortfolioOut(BaseModel):
    id: int
    name: str
    description: str | None
    initial_capital: float | None
    target_loss_threshold: float | None
    holdings: list[HoldingIn]
    # Derived status per PPTX slide 1 ("Active" = picked stocks AND computed weights)
    status: Literal["active", "inactive"]
    holding_count: int
    total_weight: float
    # Set only on PATCH responses when initial_capital changed on a portfolio
    # that already has holdings — the frontend surfaces a "recompute weights"
    # banner in that case.
    needs_recompute: bool | None = None
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


# ---------------------------------------------------------------------------
# Phase 2: VaR Full (all methods + FRTB ES)
# ---------------------------------------------------------------------------
class VarFullRequest(BaseModel):
    tickers: list[str] = Field(..., min_length=2)
    weights: list[float]
    confidence: float = Field(0.95, ge=0.9, le=0.999)
    horizon_days: int = Field(1, ge=1, le=250)
    n_paths: int = Field(10_000, ge=1000, le=100_000)
    include_garch: bool = Field(True, description="Include GARCH-t VaR (slower)")
    include_frtb: bool = Field(True, description="Include Basel FRTB ES at 97.5%")

    # Data source
    use_db_data: bool = True
    daily_returns: list[list[float]] | None = None
    cov_daily: list[list[float]] | None = None
    lookback_days: int | None = None
    risk_free_rate: float | None = None


class VarMethodResult(BaseModel):
    method: str
    confidence: float
    horizon_days: int
    var_loss: float
    cvar_loss: float | None
    portfolio_mean_daily: float
    portfolio_vol_daily: float
    simulated_paths: int | None = None


class FrtbResult(BaseModel):
    es_975: float
    var_975: float
    horizon_days: int
    confidence: float
    garch_params: dict | None = None
    n_paths: int
    fallback: str | None = None


class VarFullResponse(BaseModel):
    tickers: list[str]
    methods: dict[str, VarMethodResult]
    frtb: FrtbResult | None = None


# ---------------------------------------------------------------------------
# Phase 2: VaR Backtest (Kupiec + Christoffersen)
# ---------------------------------------------------------------------------
class BacktestRequest(BaseModel):
    tickers: list[str] = Field(..., min_length=2)
    weights: list[float]
    confidence: float = Field(0.95, ge=0.9, le=0.999)
    var_method: Literal["historical", "parametric", "monte_carlo"] = "parametric"
    window: int = Field(252, ge=60, le=2520, description="Rolling lookback window")
    significance: float = Field(0.05, ge=0.01, le=0.10)

    use_db_data: bool = True
    daily_returns: list[list[float]] | None = None
    lookback_days: int | None = None
    risk_free_rate: float | None = None


class BacktestResponse(BaseModel):
    var_method: str
    confidence: float
    n_observations: int
    n_violations: int
    expected_violations: float
    violation_rate: float
    expected_violation_rate: float

    kupiec_lr: float
    kupiec_pval: float
    pass_kupiec: bool

    christoffersen_lr: float | None
    christoffersen_pval: float | None
    pass_christoffersen: bool | None

    independence_lr: float | None
    independence_pval: float | None


# ---------------------------------------------------------------------------
# Phase 2: Correlation + Covariance Quality
# ---------------------------------------------------------------------------
class CorrelationRequest(BaseModel):
    tickers: list[str] = Field(..., min_length=2)
    use_db_data: bool = True
    daily_returns: list[list[float]] | None = None
    lookback_days: int | None = None
    risk_free_rate: float | None = None


class CovQualityReport(BaseModel):
    condition_number: float
    is_psd: bool
    min_eigenvalue: float
    max_eigenvalue: float
    trace: float
    determinant_log: float
    suggested_shrinkage: float


class CorrelationResponse(BaseModel):
    tickers: list[str]
    correlation: list[list[float]]
    correlation_parity_pass: bool
    correlation_max_diff: float
    cov_daily: list[list[float]]
    cov_daily_shrunk: list[list[float]]
    shrinkage_intensity: float
    cov_quality: CovQualityReport
    beta_raw: dict[str, float]
    beta_blume: dict[str, float]
