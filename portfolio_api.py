"""
FastAPI service exposing the Tadawul portfolio optimizer as REST endpoints.

Run locally:
    pip install fastapi uvicorn numpy scipy
    uvicorn portfolio_api:app --reload --port 8000

Endpoints:
    GET  /health                  - liveness check
    POST /api/optimize            - max Sharpe (Solver for slides 123-126)
    POST /api/frontier            - efficient frontier points
    POST /api/metrics             - Sharpe/vol/return for given weights
    GET  /docs                    - interactive Swagger UI (auto-generated)

Pair with the React frontend via CORS (already enabled for localhost:3000
and localhost:5173 for Vite). In production, lock origins to your domain.
"""
from __future__ import annotations

from typing import List, Optional
import numpy as np
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator

# Reuse the optimizer module we already built
from portfolio_optimizer import (
    PortfolioInputs,
    solve_sharpe_slsqp,
    solve_sharpe_qp,
    efficient_frontier,
    portfolio_return,
    portfolio_volatility,
    sharpe_ratio,
    TRADING_DAYS,
)

# ---------------------------------------------------------------------------
app = FastAPI(
    title="Tadawul Portfolio Optimizer API",
    description=(
        "Markowitz / CAPM / Sharpe optimization service for the "
        "Dan Analytical web platform. Implements the Solver "
        "specified on slides 123-126 of the project requirements."
    ),
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",   # Create React App
        "http://localhost:5173",   # Vite
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Request / response schemas
# ---------------------------------------------------------------------------
class OptimizeRequest(BaseModel):
    """
    Inputs for portfolio optimization.

    Either provide `cov_daily` directly (recommended - you'll have already
    computed it from the daily returns stored in the "Investment Details"
    sheet) or provide `daily_returns` and the service will compute COVAR
    using the population formula to match Excel exactly.
    """
    tickers: List[str] = Field(..., min_length=2, max_length=50,
                                examples=[["7010.SR", "2222.SR", "2010.SR",
                                            "6002.SR", "2270.SR", "1120.SR"]])
    expected_returns: List[float] = Field(..., description=(
        "Annual CAPM expected return per stock (decimals). "
        "Excel: Investment Details!P6:U6"))
    risk_free_rate: float = Field(..., ge=0, le=0.5, description=(
        "Annual risk-free rate. Excel: Dashboard!C6 (SAMA treasury)"))
    cov_daily: Optional[List[List[float]]] = Field(None, description=(
        "n x n daily covariance matrix. Excel: Optimal Portflio!R6:W11"))
    daily_returns: Optional[List[List[float]]] = Field(None, description=(
        "T x n daily return matrix (used if cov_daily is omitted)"))
    min_stock_sd: Optional[float] = Field(None, description=(
        "Constraint: portfolio SD <= this. "
        "Excel: Optimal Portflio!H9 = MIN(B11:G11). "
        "Omit to skip the constraint (pure Sharpe max)"))
    allow_shorting: bool = Field(False, description=(
        "Slide 124 says w_i >= 0, so default is False"))
    method: str = Field("slsqp", pattern="^(slsqp|qp)$", description=(
        "'slsqp' = direct Sharpe max (GRG-like); 'qp' = Cornuejols-Tutuncu QP"))

    @field_validator("expected_returns")
    @classmethod
    def _check_returns_length(cls, v, info):
        tickers = info.data.get("tickers")
        if tickers is not None and len(v) != len(tickers):
            raise ValueError("expected_returns length must match tickers")
        return v


class OptimizeResponse(BaseModel):
    success: bool
    method: str
    message: str
    weights: dict                       # {ticker: weight}
    sharpe: float
    expected_return: float
    volatility: float
    sum_weights: float


class FrontierRequest(BaseModel):
    tickers: List[str]
    expected_returns: List[float]
    risk_free_rate: float
    cov_daily: Optional[List[List[float]]] = None
    daily_returns: Optional[List[List[float]]] = None
    n_points: int = Field(50, ge=10, le=200)


class FrontierPoint(BaseModel):
    target_return: float
    volatility: float
    weights: List[float]


class FrontierResponse(BaseModel):
    points: List[FrontierPoint]
    # Also return Sharpe-optimal point so the frontend can plot the marker:
    tangency_return: float
    tangency_volatility: float
    tangency_weights: dict


class MetricsRequest(BaseModel):
    weights: List[float]
    expected_returns: List[float]
    risk_free_rate: float
    cov_daily: List[List[float]]
    tickers: Optional[List[str]] = None


class MetricsResponse(BaseModel):
    sharpe: float
    expected_return: float
    volatility: float
    sum_weights: float
    # Per-stock contribution to risk (useful for the dashboard's risk waterfall)
    risk_contribution: dict


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _build_inputs(
    tickers: List[str],
    expected_returns: List[float],
    risk_free_rate: float,
    cov_daily: Optional[List[List[float]]],
    daily_returns: Optional[List[List[float]]],
    min_stock_sd: Optional[float] = None,
    allow_shorting: bool = False,
) -> PortfolioInputs:
    """Build PortfolioInputs, computing cov_daily from returns if needed."""
    if cov_daily is None and daily_returns is None:
        raise HTTPException(400,
            "Provide either cov_daily or daily_returns.")

    if cov_daily is None:
        rets = np.asarray(daily_returns, dtype=float)
        if rets.ndim != 2 or rets.shape[1] != len(tickers):
            raise HTTPException(400,
                f"daily_returns must be T x {len(tickers)}, got {rets.shape}")
        # ddof=0 matches Excel's COVAR (population, not sample)
        cov_mat = np.cov(rets, rowvar=False, ddof=0)
    else:
        cov_mat = np.asarray(cov_daily, dtype=float)

    return PortfolioInputs(
        tickers=tickers,
        expected_returns=np.asarray(expected_returns, dtype=float),
        cov_daily=cov_mat,
        risk_free_rate=risk_free_rate,
        min_stock_sd=min_stock_sd,
        allow_shorting=allow_shorting,
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@app.get("/health")
def health():
    return {"status": "ok", "service": "tadawul-portfolio-optimizer"}


@app.post("/api/optimize", response_model=OptimizeResponse)
def optimize(req: OptimizeRequest):
    """
    Run the Solver defined on slides 123-126.

    Objective : max Sharpe = (R_p - R_f) / sigma_p
    Subject to: sum(w) = 1, w_i >= 0, sigma_p <= min_sd, R_p >= R_f
    """
    inputs = _build_inputs(
        req.tickers, req.expected_returns, req.risk_free_rate,
        req.cov_daily, req.daily_returns,
        req.min_stock_sd, req.allow_shorting,
    )

    try:
        if req.method == "qp":
            result = solve_sharpe_qp(inputs)
        else:
            result = solve_sharpe_slsqp(inputs)
    except ValueError as e:
        raise HTTPException(400, str(e))

    # Clean numpy types for JSON
    clean_weights = {k: float(v) for k, v in result["weights"].items()}
    return OptimizeResponse(
        success=result["success"],
        method=result["method"],
        message=str(result["message"]),
        weights=clean_weights,
        sharpe=float(result["sharpe"]),
        expected_return=float(result["expected_return"]),
        volatility=float(result["volatility"]),
        sum_weights=float(result["sum_weights"]),
    )


@app.post("/api/frontier", response_model=FrontierResponse)
def frontier(req: FrontierRequest):
    """Return points along the Efficient Frontier for the dashboard chart."""
    inputs = _build_inputs(
        req.tickers, req.expected_returns, req.risk_free_rate,
        req.cov_daily, req.daily_returns,
    )

    points = efficient_frontier(inputs, n_points=req.n_points)

    # Also compute tangency portfolio (Sharpe-optimal) for the chart marker
    tangency = solve_sharpe_slsqp(
        inputs,
        enforce_min_sd_constraint=False,
        enforce_return_floor=False,
    )

    return FrontierResponse(
        points=[FrontierPoint(**p) for p in points],
        tangency_return=float(tangency["expected_return"]),
        tangency_volatility=float(tangency["volatility"]),
        tangency_weights={k: float(v) for k, v in tangency["weights"].items()},
    )


@app.post("/api/metrics", response_model=MetricsResponse)
def metrics(req: MetricsRequest):
    """
    Compute Sharpe/return/vol for a user-specified weight vector.
    Called by the dashboard when users drag the 'Edit Weight' sliders
    (Excel: Optimal Portflio!E2:E7).
    """
    w = np.asarray(req.weights, dtype=float)
    mu = np.asarray(req.expected_returns, dtype=float)
    cov_a = np.asarray(req.cov_daily, dtype=float) * TRADING_DAYS

    if not (len(w) == len(mu) == cov_a.shape[0] == cov_a.shape[1]):
        raise HTTPException(400, "Dimension mismatch across weights/returns/cov")

    r = portfolio_return(w, mu)
    v = portfolio_volatility(w, cov_a)
    s = sharpe_ratio(w, mu, cov_a, req.risk_free_rate)

    # Risk contribution: w_i * (Sigma @ w)_i / sigma_p^2  (Euler decomposition)
    marginal = cov_a @ w
    total_var = float(w @ marginal)
    if total_var > 1e-12:
        rc = w * marginal / total_var
    else:
        rc = np.zeros_like(w)

    labels = req.tickers or [f"stock_{i+1}" for i in range(len(w))]
    risk_contribution = {labels[i]: float(rc[i]) for i in range(len(w))}

    return MetricsResponse(
        sharpe=float(s),
        expected_return=float(r),
        volatility=float(v),
        sum_weights=float(w.sum()),
        risk_contribution=risk_contribution,
    )
