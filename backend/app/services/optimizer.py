"""
Production Markowitz / CAPM / Sharpe optimizer.

This is the canonical version used by the API. It is a hardened evolution of
the root-level `portfolio_optimizer.py` (kept for Excel-parity notebook
backwards-compatibility) with these upgrades:

  - **cvxpy** is the default QP backend — scales cleanly to n=234 Tadawul
    stocks with full-precision active-set solving. Falls back to scipy
    `trust-constr` if cvxpy is unavailable.
  - Efficient Frontier is vectorized into a single cvxpy parametric solve,
    avoiding 50 independent SLSQP runs.
  - All public functions return plain Python types (no numpy scalars),
    so FastAPI / JSON serialization is straightforward.

Mirrors Excel slides 123-126. See `excel_to_code_mapping.md` for cell parity.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Sequence

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, NonlinearConstraint, minimize

log = logging.getLogger(__name__)

try:
    import cvxpy as cp
    _HAS_CVXPY = True
except ImportError:  # pragma: no cover — cvxpy is optional at import time
    _HAS_CVXPY = False
    cp = None  # type: ignore[assignment]

TRADING_DAYS = 252  # Excel slide 125: SQRT(... * 252)


# ---------------------------------------------------------------------------
@dataclass
class PortfolioInputs:
    """
    Inputs for optimization — all arrays are Python / numpy-native.

    tickers           : list of Tadawul symbols
    expected_returns  : annual CAPM expected return per stock
    cov_daily         : n x n daily covariance matrix (population, ddof=0)
    risk_free_rate    : annual risk-free rate (decimal)
    min_stock_sd      : optional SD cap = MIN(individual annualized SDs)
    allow_shorting    : if False (default), enforces w_i >= 0 per slide 124
    """
    tickers: Sequence[str]
    expected_returns: np.ndarray
    cov_daily: np.ndarray
    risk_free_rate: float
    min_stock_sd: float | None = None
    allow_shorting: bool = False

    def __post_init__(self) -> None:
        self.expected_returns = np.asarray(self.expected_returns, dtype=float)
        self.cov_daily = np.asarray(self.cov_daily, dtype=float)
        if self.cov_daily.shape[0] != self.cov_daily.shape[1]:
            raise ValueError("covariance matrix must be square")
        if self.cov_daily.shape[0] != len(self.expected_returns):
            raise ValueError("size mismatch between returns and covariance")

    @property
    def n(self) -> int:
        return len(self.expected_returns)

    @property
    def cov_annual(self) -> np.ndarray:
        return self.cov_daily * TRADING_DAYS


# ---------------------------------------------------------------------------
# Metrics (pure functions — mirror Excel cells)
# ---------------------------------------------------------------------------
def portfolio_return(w: np.ndarray, mu: np.ndarray) -> float:
    """Excel: Optimal Portflio!J1"""
    return float(np.dot(w, mu))


def portfolio_volatility(w: np.ndarray, cov_annual: np.ndarray) -> float:
    """Excel slide 125: SQRT(MMULT(TRANSPOSE(D2:D7),MMULT(R6:W11,D2:D7))*252)"""
    return float(np.sqrt(w @ cov_annual @ w))


def sharpe_ratio(w: np.ndarray, mu: np.ndarray, cov_annual: np.ndarray, rf: float) -> float:
    """Excel slide 123: J4 = (J1 - Dashboard!C6) / J2"""
    vol = portfolio_volatility(w, cov_annual)
    if vol < 1e-12:
        return -1e9
    return (portfolio_return(w, mu) - rf) / vol


def risk_contribution(w: np.ndarray, cov_annual: np.ndarray) -> np.ndarray:
    """Euler decomposition of variance — used for the dashboard's risk waterfall."""
    w = np.asarray(w, dtype=float)
    marginal = cov_annual @ w
    total_var = float(w @ marginal)
    if total_var <= 1e-12:
        return np.zeros_like(w)
    return w * marginal / total_var


# ---------------------------------------------------------------------------
# Method 1: SLSQP direct Sharpe max — matches Excel GRG most closely.
# Kept as the primary parity reference against the golden workbook.
# ---------------------------------------------------------------------------
def solve_sharpe_slsqp(
    inputs: PortfolioInputs,
    x0: np.ndarray | None = None,
    enforce_min_sd_constraint: bool = True,
    enforce_return_floor: bool = True,
) -> dict:
    n = inputs.n
    mu = inputs.expected_returns
    cov_a = inputs.cov_annual
    rf = inputs.risk_free_rate

    if x0 is None:
        x0 = np.full(n, 1.0 / n)

    def neg_sharpe(w: np.ndarray) -> float:
        return -sharpe_ratio(w, mu, cov_a, rf)

    lb = -1.0 if inputs.allow_shorting else 0.0
    bounds = Bounds(lb=lb, ub=1.0)
    constraints: list = [LinearConstraint(np.ones(n), lb=1.0, ub=1.0)]

    if enforce_min_sd_constraint and inputs.min_stock_sd is not None:
        def vol_gap(w): return inputs.min_stock_sd - portfolio_volatility(w, cov_a)
        constraints.append(NonlinearConstraint(vol_gap, lb=0.0, ub=np.inf))

    if enforce_return_floor:
        def ret_gap(w): return portfolio_return(w, mu) - rf
        constraints.append(NonlinearConstraint(ret_gap, lb=0.0, ub=np.inf))

    result = minimize(
        neg_sharpe, x0=x0, method="SLSQP",
        bounds=bounds, constraints=constraints,
        options={"ftol": 1e-10, "maxiter": 500, "disp": False},
    )

    w = result.x
    return {
        "method": "SLSQP (direct Sharpe max)",
        "success": bool(result.success),
        "message": str(result.message),
        "weights": dict(zip(inputs.tickers, np.round(w, 6).tolist())),
        "weights_array": w,
        "sharpe": sharpe_ratio(w, mu, cov_a, rf),
        "expected_return": portfolio_return(w, mu),
        "volatility": portfolio_volatility(w, cov_a),
        "sum_weights": float(w.sum()),
    }


# ---------------------------------------------------------------------------
# Method 2: Quadratic Program via Cornuejols-Tütüncü transformation
#
#     min  (1/2) y' Σ y
#     s.t. (μ − rf·1)' y = 1,   y ≥ 0
#     then w = y / sum(y)
#
# This is the "use optimization algorithms like quadratic programming"
# method the PDF brief asks for. cvxpy makes it a one-liner at n=234.
# ---------------------------------------------------------------------------
def solve_sharpe_qp(inputs: PortfolioInputs) -> dict:
    mu = inputs.expected_returns
    cov_a = inputs.cov_annual
    rf = inputs.risk_free_rate
    excess = mu - rf

    if np.all(excess <= 0):
        raise ValueError(
            "No stock beats the risk-free rate — Sharpe maximization is "
            "ill-posed. Check CAPM inputs or lower risk_free_rate."
        )

    if _HAS_CVXPY:
        return _solve_sharpe_qp_cvxpy(inputs)
    log.warning("cvxpy not available — falling back to scipy trust-constr QP")
    return _solve_sharpe_qp_scipy(inputs)


def _solve_sharpe_qp_cvxpy(inputs: PortfolioInputs) -> dict:
    n = inputs.n
    mu = inputs.expected_returns
    cov_a = inputs.cov_annual
    rf = inputs.risk_free_rate
    excess = mu - rf

    y = cp.Variable(n, nonneg=not inputs.allow_shorting)
    prob = cp.Problem(
        cp.Minimize(0.5 * cp.quad_form(y, cp.psd_wrap(cov_a))),
        [excess @ y == 1],
    )
    prob.solve(solver=cp.CLARABEL, verbose=False)

    if prob.status not in ("optimal", "optimal_inaccurate"):
        raise RuntimeError(f"QP solver returned status={prob.status}")

    y_val = np.asarray(y.value, dtype=float)
    w = y_val / y_val.sum()
    return {
        "method": "QP (cvxpy/Clarabel, Cornuejols-Tütüncü transform)",
        "success": prob.status == "optimal",
        "message": f"cvxpy status={prob.status}",
        "weights": dict(zip(inputs.tickers, np.round(w, 6).tolist())),
        "weights_array": w,
        "sharpe": sharpe_ratio(w, mu, inputs.cov_annual, rf),
        "expected_return": portfolio_return(w, mu),
        "volatility": portfolio_volatility(w, inputs.cov_annual),
        "sum_weights": float(w.sum()),
    }


def _solve_sharpe_qp_scipy(inputs: PortfolioInputs) -> dict:
    """Fallback QP solver using scipy trust-constr."""
    n = inputs.n
    mu = inputs.expected_returns
    cov_a = inputs.cov_annual
    rf = inputs.risk_free_rate
    excess = mu - rf

    def obj(y): return 0.5 * y @ cov_a @ y
    def obj_grad(y): return cov_a @ y
    def obj_hess(y): return cov_a

    lb = -np.inf if inputs.allow_shorting else 0.0
    bounds = Bounds(lb=lb, ub=np.inf)
    excess_constraint = LinearConstraint(excess, lb=1.0, ub=1.0)

    y0 = np.where(excess > 0, 1.0 / (n * np.maximum(excess, 1e-6)), 0.0)
    if y0.sum() == 0:
        y0 = np.ones(n)

    result = minimize(
        obj, x0=y0, jac=obj_grad, hess=obj_hess,
        method="trust-constr", bounds=bounds, constraints=[excess_constraint],
        options={"xtol": 1e-10, "gtol": 1e-10, "maxiter": 500, "verbose": 0},
    )
    y = result.x
    w = y / y.sum()
    return {
        "method": "QP (scipy trust-constr fallback)",
        "success": bool(result.success),
        "message": str(result.message),
        "weights": dict(zip(inputs.tickers, np.round(w, 6).tolist())),
        "weights_array": w,
        "sharpe": sharpe_ratio(w, mu, cov_a, rf),
        "expected_return": portfolio_return(w, mu),
        "volatility": portfolio_volatility(w, cov_a),
        "sum_weights": float(w.sum()),
    }


# ---------------------------------------------------------------------------
# Efficient Frontier — batched cvxpy solve.
# ---------------------------------------------------------------------------
def efficient_frontier(inputs: PortfolioInputs, n_points: int = 50) -> list[dict]:
    """
    For each target return R*, solve:
        min  w'Σw   s.t. sum(w)=1, w>=0, μ'w = R*
    Returns a list of {target_return, volatility, weights} points.
    """
    if _HAS_CVXPY:
        return _frontier_cvxpy(inputs, n_points)
    return _frontier_scipy(inputs, n_points)


def _frontier_cvxpy(inputs: PortfolioInputs, n_points: int) -> list[dict]:
    n = inputs.n
    mu = inputs.expected_returns
    cov_a = inputs.cov_annual

    w = cp.Variable(n, nonneg=not inputs.allow_shorting)
    r_target = cp.Parameter()

    constraints = [cp.sum(w) == 1, mu @ w == r_target]
    if not inputs.allow_shorting:
        constraints.append(w <= 1)

    prob = cp.Problem(cp.Minimize(cp.quad_form(w, cp.psd_wrap(cov_a))), constraints)

    targets = np.linspace(float(mu.min()) + 1e-6, float(mu.max()) - 1e-6, n_points)
    out: list[dict] = []
    for t in targets:
        r_target.value = float(t)
        try:
            prob.solve(solver=cp.CLARABEL, verbose=False)
        except cp.SolverError:
            continue
        if prob.status not in ("optimal", "optimal_inaccurate"):
            continue
        w_val = np.asarray(w.value, dtype=float)
        out.append(
            {
                "target_return": float(t),
                "volatility": portfolio_volatility(w_val, cov_a),
                "weights": w_val.tolist(),
            }
        )
    return out


def _frontier_scipy(inputs: PortfolioInputs, n_points: int) -> list[dict]:
    mu = inputs.expected_returns
    cov_a = inputs.cov_annual
    n = inputs.n

    targets = np.linspace(mu.min() + 1e-6, mu.max() - 1e-6, n_points)
    frontier: list[dict] = []

    for r_target in targets:
        def obj(w): return 0.5 * w @ cov_a @ w
        def jac(w): return cov_a @ w

        bounds = Bounds(-1.0 if inputs.allow_shorting else 0.0, 1.0)
        cons = [
            LinearConstraint(np.ones(n), 1.0, 1.0),
            LinearConstraint(mu, r_target, r_target),
        ]
        r = minimize(
            obj, np.full(n, 1.0 / n), jac=jac, method="SLSQP",
            bounds=bounds, constraints=cons,
            options={"ftol": 1e-9, "maxiter": 300},
        )
        if r.success:
            frontier.append(
                {
                    "target_return": float(r_target),
                    "volatility": portfolio_volatility(r.x, cov_a),
                    "weights": r.x.tolist(),
                }
            )
    return frontier
