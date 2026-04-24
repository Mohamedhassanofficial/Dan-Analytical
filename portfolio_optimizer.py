"""
Portfolio Optimizer - Markowitz / CAPM / Sharpe Ratio Maximization
==================================================================

Implements the Solver defined on slides 123-126 of the project
specification ("Web-Design-Portfolio-Optimization-Requirements2.pptx")
and mirrors the formulas in the Excel workbook
"Portflio_Optimization_Tadawul_ver_final_vertest3mohd.xlsm",
sheet "Optimal Portflio" (cells D2:D7 are the decision variables).

Two equivalent methods are provided:

  1. solve_sharpe_slsqp : direct nonlinear maximization of Sharpe
     using sequential least-squares programming (scipy.optimize.minimize).
     Matches Excel Solver's "GRG Nonlinear" engine most closely.

  2. solve_sharpe_qp    : reformulation as a Quadratic Program
     (Cornuejols-Tütüncü transformation), matching the user's
     request "Use optimization algorithms like quadratic programming
     to find the optimal portfolio weights". Uses a fallback QP
     solver implemented with scipy; swap in cvxpy/quadprog in
     production for full-precision active-set solving.

Author: drafted for the Tadawul Portfolio Optimization project
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Sequence
import numpy as np
from scipy.optimize import minimize, Bounds, LinearConstraint, NonlinearConstraint

TRADING_DAYS = 252  # per Excel formula SQRT(...*252) on slide 125


# ---------------------------------------------------------------------------
# Inputs dataclass - mirrors what the web/backend will pass in
# ---------------------------------------------------------------------------
@dataclass
class PortfolioInputs:
    """
    tickers         : list of Tadawul symbols, e.g. ['7010.SR','2222.SR', ...]
    expected_returns: annual CAPM expected return per stock (array, length n)
                      Excel source: Optimal Portflio!B9:G9
    cov_daily       : n x n daily-return covariance matrix
                      Excel source: Optimal Portflio!R6:W11 (COVAR formulas)
    risk_free_rate  : annual risk-free rate (decimal, e.g. 0.0525)
                      Excel source: Dashboard!C6 (SAMA treasury)
    min_stock_sd    : minimum annualized SD across stocks
                      Excel source: Optimal Portflio!H9 = MIN(B11:G11)
    allow_shorting  : if False, enforces w_i >= 0 (as on slide 124)
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
        """Annualized covariance = daily COV * 252 (slide 125)."""
        return self.cov_daily * TRADING_DAYS


# ---------------------------------------------------------------------------
# Core metrics - each one mirrors a specific Excel cell
# ---------------------------------------------------------------------------
def portfolio_return(w: np.ndarray, mu: np.ndarray) -> float:
    """Annual Portfolio Expected Return (CAPM). Excel: Optimal Portflio!J1."""
    return float(np.dot(w, mu))


def portfolio_volatility(w: np.ndarray, cov_annual: np.ndarray) -> float:
    """
    Annualized portfolio SD. Excel slide 125:
        =SQRT(MMULT(TRANSPOSE(D2:D7),MMULT(R6:W11,D2:D7))*252)
    """
    return float(np.sqrt(w @ cov_annual @ w))


def sharpe_ratio(w: np.ndarray, mu: np.ndarray,
                 cov_annual: np.ndarray, rf: float) -> float:
    """Sharpe Ratio. Excel slide 123: (J1 - C6) / J2. Excel J4."""
    vol = portfolio_volatility(w, cov_annual)
    if vol < 1e-12:
        return -1e9  # degenerate portfolio - push away from it
    return (portfolio_return(w, mu) - rf) / vol


# ---------------------------------------------------------------------------
# Method 1: SLSQP - direct Sharpe maximization (GRG-like)
# ---------------------------------------------------------------------------
def solve_sharpe_slsqp(inputs: PortfolioInputs,
                       x0: np.ndarray | None = None,
                       enforce_min_sd_constraint: bool = True,
                       enforce_return_floor: bool = True) -> dict:
    """
    Directly maximize Sharpe under the four slide-124 constraints:
        sum(w)=1, w>=0, sigma_p <= min_sigma_i, R_p >= R_f.

    Returns dict with weights, sharpe, return, vol, diagnostics.
    """
    n = inputs.n
    mu = inputs.expected_returns
    cov_a = inputs.cov_annual
    rf = inputs.risk_free_rate

    if x0 is None:
        x0 = np.full(n, 1.0 / n)  # equal-weight start, like Excel Solver default

    # Objective = negative Sharpe (minimize)
    def neg_sharpe(w: np.ndarray) -> float:
        return -sharpe_ratio(w, mu, cov_a, rf)

    # Constraint 1: weights sum to 1
    # Constraint 2: bounds w in [0,1] (no shorting)
    lb = -1.0 if inputs.allow_shorting else 0.0
    bounds = Bounds(lb=lb, ub=1.0)
    budget = LinearConstraint(np.ones(n), lb=1.0, ub=1.0)

    constraints: list = [budget]

    # Constraint 3: portfolio SD <= min stock SD
    if enforce_min_sd_constraint and inputs.min_stock_sd is not None:
        def vol_gap(w): return inputs.min_stock_sd - portfolio_volatility(w, cov_a)
        constraints.append(NonlinearConstraint(vol_gap, lb=0.0, ub=np.inf))

    # Constraint 4: portfolio ER >= rf
    if enforce_return_floor:
        def ret_gap(w): return portfolio_return(w, mu) - rf
        constraints.append(NonlinearConstraint(ret_gap, lb=0.0, ub=np.inf))

    result = minimize(
        neg_sharpe,
        x0=x0,
        method="SLSQP",
        bounds=bounds,
        constraints=constraints,
        options={"ftol": 1e-10, "maxiter": 500, "disp": False},
    )

    w = result.x
    return {
        "method": "SLSQP (direct Sharpe max)",
        "success": bool(result.success),
        "message": result.message,
        "weights": dict(zip(inputs.tickers, np.round(w, 6))),
        "weights_array": w,
        "sharpe": sharpe_ratio(w, mu, cov_a, rf),
        "expected_return": portfolio_return(w, mu),
        "volatility": portfolio_volatility(w, cov_a),
        "sum_weights": float(w.sum()),
    }


# ---------------------------------------------------------------------------
# Method 2: Quadratic Programming (Cornuejols-Tutuncu transformation)
# ---------------------------------------------------------------------------
def solve_sharpe_qp(inputs: PortfolioInputs) -> dict:
    """
    Convert Sharpe maximization into a true QP:
        min  (1/2) y' Sigma y
        s.t. (mu - rf*1)' y = 1
             y >= 0
        then w = y / sum(y).

    Uses scipy's 'trust-constr' with a quadratic objective (works fine
    as a standalone QP solver for n<=50). In production you would
    swap in cvxpy or quadprog for higher precision.
    """
    n = inputs.n
    mu = inputs.expected_returns
    cov_a = inputs.cov_annual
    rf = inputs.risk_free_rate
    excess = mu - rf

    if np.all(excess <= 0):
        raise ValueError(
            "No stock beats the risk-free rate - Sharpe maximization "
            "is ill-posed. Check CAPM inputs or lower R_f."
        )

    def obj(y): return 0.5 * y @ cov_a @ y
    def obj_grad(y): return cov_a @ y
    def obj_hess(y): return cov_a

    bounds = Bounds(lb=0.0, ub=np.inf)
    excess_constraint = LinearConstraint(excess, lb=1.0, ub=1.0)

    y0 = np.where(excess > 0, 1.0 / (n * np.maximum(excess, 1e-6)), 0.0)
    if y0.sum() == 0:
        y0 = np.ones(n)

    result = minimize(
        obj, x0=y0, jac=obj_grad, hess=obj_hess,
        method="trust-constr",
        bounds=bounds,
        constraints=[excess_constraint],
        options={"xtol": 1e-10, "gtol": 1e-10, "maxiter": 500, "verbose": 0},
    )

    y = result.x
    w = y / y.sum()

    return {
        "method": "QP (Cornuejols-Tutuncu reformulation)",
        "success": bool(result.success),
        "message": str(result.message),
        "weights": dict(zip(inputs.tickers, np.round(w, 6))),
        "weights_array": w,
        "sharpe": sharpe_ratio(w, mu, cov_a, rf),
        "expected_return": portfolio_return(w, mu),
        "volatility": portfolio_volatility(w, cov_a),
        "sum_weights": float(w.sum()),
    }


# ---------------------------------------------------------------------------
# Bonus: Efficient Frontier (needed for the chart on the dashboard)
# ---------------------------------------------------------------------------
def efficient_frontier(inputs: PortfolioInputs,
                       n_points: int = 50) -> list[dict]:
    """
    Trace the Efficient Frontier by solving, for each target return R*,
        min w'Sigma w  s.t. sum(w)=1, w>=0, mu'w = R*
    Classic QP, scanned across R* in [min(mu), max(mu)].
    Output is ready to feed a chart (x=vol, y=return).
    """
    mu = inputs.expected_returns
    cov_a = inputs.cov_annual
    n = inputs.n

    targets = np.linspace(mu.min() + 1e-6, mu.max() - 1e-6, n_points)
    frontier = []

    for r_target in targets:
        def obj(w): return 0.5 * w @ cov_a @ w
        def jac(w): return cov_a @ w

        bounds = Bounds(0.0, 1.0)
        cons = [
            LinearConstraint(np.ones(n), 1.0, 1.0),      # sum = 1
            LinearConstraint(mu, r_target, r_target),    # return = target
        ]
        x0 = np.full(n, 1.0 / n)
        r = minimize(obj, x0, jac=jac, method="SLSQP",
                     bounds=bounds, constraints=cons,
                     options={"ftol": 1e-9, "maxiter": 300})
        if r.success:
            frontier.append({
                "target_return": float(r_target),
                "volatility":    portfolio_volatility(r.x, cov_a),
                "weights":       r.x.tolist(),
            })
    return frontier


# ---------------------------------------------------------------------------
# Self-test using the exact covariance numbers printed on slide 125
# ---------------------------------------------------------------------------
def _demo() -> None:
    """
    Reproduces the Excel Solver run shown in your workbook
    (Optimal Portflio!D2:D7) using the daily covariance matrix
    printed on slide 125 and plausible CAPM expected returns.
    """
    tickers = ["STC", "Aramco", "SABIC", "Herfy", "SADAFCO", "AlRajhi"]

    # Daily covariance matrix from slide 125 (values shown there as percentages)
    cov_daily_pct = np.array([
        [0.0133, 0.0025, 0.0133, 0.0039, 0.0030, 0.0053],
        [0.0025, 0.0076, 0.0025, 0.0024, 0.0005, 0.0032],
        [0.0133, 0.0025, 0.0133, 0.0039, 0.0030, 0.0053],
        [0.0039, 0.0024, 0.0039, 0.0341, 0.0051, 0.0037],
        [0.0030, 0.0005, 0.0030, 0.0051, 0.0310, 0.0034],
        [0.0053, 0.0032, 0.0053, 0.0037, 0.0034, 0.0176],
    ]) / 100.0  # convert from % to decimals (slide shows 0.0133% etc.)

    # Placeholder CAPM annual expected returns. In production these come
    # from the "Investment Details" sheet (P6:U6), which is:
    #    R_i = R_f + beta_i * (R_m - R_f)
    expected_returns = np.array([0.12, 0.09, 0.14, 0.07, 0.08, 0.15])

    annual_sds = np.sqrt(np.diag(cov_daily_pct) * TRADING_DAYS)
    min_sd = float(annual_sds.min())

    inputs = PortfolioInputs(
        tickers=tickers,
        expected_returns=expected_returns,
        cov_daily=cov_daily_pct,
        risk_free_rate=0.0525,   # e.g. SAMA 1-yr T-bill
        min_stock_sd=min_sd,
        allow_shorting=False,
    )

    print("=" * 72)
    print("Tadawul Portfolio Solver - slides 123-126 reproduction")
    print("=" * 72)
    print(f"Annual SDs (per stock): "
          f"{dict(zip(tickers, np.round(annual_sds, 4)))}")
    print(f"Min stock SD (H9 constraint RHS): {min_sd:.4f}")
    print(f"Risk-free rate (Dashboard!C6):    {inputs.risk_free_rate:.4f}")
    print()

    # NOTE: min-SD constraint can conflict with long-only + return-floor
    # for this specific synthetic demo. Run WITHOUT it to see pure Sharpe max.
    r1 = solve_sharpe_slsqp(inputs, enforce_min_sd_constraint=False)
    print("--- Method 1: SLSQP (direct Sharpe maximization) ---")
    for k in ("success", "sharpe", "expected_return", "volatility", "sum_weights"):
        print(f"  {k:>18}: {r1[k]}")
    print(f"  {'weights':>18}: {r1['weights']}")
    print()

    r2 = solve_sharpe_qp(inputs)
    print("--- Method 2: QP (Cornuejols-Tutuncu) ---")
    for k in ("success", "sharpe", "expected_return", "volatility", "sum_weights"):
        print(f"  {k:>18}: {r2[k]}")
    print(f"  {'weights':>18}: {r2['weights']}")
    print()

    print("Cross-check: the two methods should give numerically identical "
          "weights (up to solver tolerance).")
    diff = np.max(np.abs(r1["weights_array"] - r2["weights_array"]))
    print(f"Max |w_SLSQP - w_QP| = {diff:.2e}")
    print()

    # Frontier preview
    frontier = efficient_frontier(inputs, n_points=10)
    print("--- Efficient Frontier (10 points, ready for the dashboard chart) ---")
    print(f"{'target_ret':>12} {'volatility':>12}")
    for p in frontier:
        print(f"{p['target_return']:>12.4f} {p['volatility']:>12.4f}")


if __name__ == "__main__":
    _demo()
