"""
Optimizer sanity + parity tests.

The canonical parity run lives in `excel_parity_test.ipynb` (Jupyter). This
module covers the headline invariants:

  - SLSQP and QP agree on a clean 6-stock problem
  - Weights sum to 1, are non-negative (long-only), and a reasonable Sharpe
  - Efficient frontier is monotone in return → volatility
  - CAPM expected-return + covariance annualization behave as expected
"""
from __future__ import annotations

import numpy as np
import pytest

from app.services.optimizer import (
    PortfolioInputs,
    TRADING_DAYS,
    efficient_frontier,
    portfolio_return,
    portfolio_volatility,
    sharpe_ratio,
    solve_sharpe_qp,
    solve_sharpe_slsqp,
)


# Fixture mirrors the Excel slide-125 numbers (6-stock Tadawul demo).
@pytest.fixture(scope="module")
def inputs_6() -> PortfolioInputs:
    tickers = ["STC", "Aramco", "SABIC", "Herfy", "SADAFCO", "AlRajhi"]
    cov_daily = np.array([
        [0.0133, 0.0025, 0.0133, 0.0039, 0.0030, 0.0053],
        [0.0025, 0.0076, 0.0025, 0.0024, 0.0005, 0.0032],
        [0.0133, 0.0025, 0.0133, 0.0039, 0.0030, 0.0053],
        [0.0039, 0.0024, 0.0039, 0.0341, 0.0051, 0.0037],
        [0.0030, 0.0005, 0.0030, 0.0051, 0.0310, 0.0034],
        [0.0053, 0.0032, 0.0053, 0.0037, 0.0034, 0.0176],
    ]) / 100.0
    mu = np.array([0.12, 0.09, 0.14, 0.07, 0.08, 0.15])
    return PortfolioInputs(
        tickers=tickers,
        expected_returns=mu,
        cov_daily=cov_daily,
        risk_free_rate=0.0525,
        allow_shorting=False,
    )


def test_slsqp_basic(inputs_6):
    r = solve_sharpe_slsqp(inputs_6, enforce_min_sd_constraint=False)
    assert r["success"]
    w = r["weights_array"]
    assert abs(w.sum() - 1.0) < 1e-6
    assert (w >= -1e-8).all()          # long-only
    assert r["sharpe"] > 0             # should beat risk-free
    assert r["expected_return"] > inputs_6.risk_free_rate


def test_qp_basic(inputs_6):
    r = solve_sharpe_qp(inputs_6)
    assert r["success"]
    w = r["weights_array"]
    assert abs(w.sum() - 1.0) < 1e-6
    assert (w >= -1e-6).all()


def test_slsqp_qp_agree(inputs_6):
    """Two equivalent methods should hit the same Sharpe within tolerance."""
    r1 = solve_sharpe_slsqp(inputs_6, enforce_min_sd_constraint=False)
    r2 = solve_sharpe_qp(inputs_6)
    assert abs(r1["sharpe"] - r2["sharpe"]) < 1e-4


def test_metrics_are_consistent(inputs_6):
    """J1, J2, J4 from Excel must compose correctly in Python."""
    mu = inputs_6.expected_returns
    cov_a = inputs_6.cov_annual
    rf = inputs_6.risk_free_rate

    w = np.full(inputs_6.n, 1.0 / inputs_6.n)
    r = portfolio_return(w, mu)
    v = portfolio_volatility(w, cov_a)
    s = sharpe_ratio(w, mu, cov_a, rf)

    assert r == pytest.approx(float(np.dot(w, mu)))
    assert v == pytest.approx(float(np.sqrt(w @ cov_a @ w)))
    assert s == pytest.approx((r - rf) / v)


def test_annualization(inputs_6):
    """cov_annual = cov_daily * 252 (Excel slide 125)."""
    assert np.allclose(inputs_6.cov_annual, inputs_6.cov_daily * TRADING_DAYS)


def test_efficient_frontier_monotone(inputs_6):
    """On the efficient frontier, higher target return → higher volatility."""
    pts = efficient_frontier(inputs_6, n_points=20)
    assert len(pts) >= 10
    # Most of the curve should be monotone; allow a tiny fraction of wobble
    rets = np.array([p["target_return"] for p in pts])
    vols = np.array([p["volatility"] for p in pts])
    order = np.argsort(rets)
    vols = vols[order]
    monotone = np.sum(np.diff(vols) >= -1e-4)
    assert monotone >= (len(vols) - 2) * 0.8


def test_short_circuit_when_no_excess_return():
    """QP should raise when no stock beats the risk-free rate."""
    n = 3
    mu = np.array([0.02, 0.02, 0.02])
    cov = np.eye(n) * 0.01
    inputs = PortfolioInputs(
        tickers=list("ABC"),
        expected_returns=mu,
        cov_daily=cov / 252,
        risk_free_rate=0.05,
    )
    with pytest.raises(ValueError, match="No stock beats"):
        solve_sharpe_qp(inputs)
