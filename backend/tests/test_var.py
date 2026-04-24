"""VaR sanity tests — three methods should roughly agree on a normal dataset."""
from __future__ import annotations

import numpy as np
import pytest

from app.services.var import (
    compute_all,
    historical_var,
    monte_carlo_var,
    parametric_var,
)


@pytest.fixture(scope="module")
def normal_returns() -> np.ndarray:
    rng = np.random.default_rng(42)
    # 3 assets, 5 years of "trading days"
    n_assets = 3
    n_days = 1260
    mu = np.array([0.0003, 0.0004, 0.00025])  # ~7-10% annual
    cov = np.array([
        [0.00015, 0.00005, 0.00004],
        [0.00005, 0.00020, 0.00006],
        [0.00004, 0.00006, 0.00012],
    ])
    return rng.multivariate_normal(mu, cov, size=n_days)


def test_three_methods_agree_on_normal_data(normal_returns):
    w = np.array([0.4, 0.35, 0.25])
    all_ = compute_all(w, normal_returns, confidence=0.95, horizon_days=1, n_paths=20_000)

    # For clean Gaussian data, all three methods should be within ~20% of each other
    var_hist = all_["historical"].var_loss
    var_param = all_["parametric"].var_loss
    var_mc = all_["monte_carlo"].var_loss

    for a, b in [(var_hist, var_param), (var_hist, var_mc), (var_param, var_mc)]:
        assert abs(a - b) / max(a, b, 1e-8) < 0.20, (a, b)


def test_var_scales_with_sqrt_horizon(normal_returns):
    w = np.array([0.4, 0.35, 0.25])
    v1 = parametric_var(w, daily_returns=normal_returns, confidence=0.95, horizon_days=1)
    v10 = parametric_var(w, daily_returns=normal_returns, confidence=0.95, horizon_days=10)
    # 10-day VaR ≈ 1-day VaR * sqrt(10) under normality + drift (tolerate drift)
    ratio = v10.var_loss / v1.var_loss
    assert 2.8 < ratio < 3.8  # sqrt(10) ≈ 3.16


def test_cvar_greater_than_var(normal_returns):
    """Expected shortfall is always ≥ VaR."""
    w = np.array([0.5, 0.3, 0.2])
    h = historical_var(w, normal_returns, confidence=0.95)
    p = parametric_var(w, daily_returns=normal_returns, confidence=0.95)
    mc = monte_carlo_var(w, daily_returns=normal_returns, confidence=0.95, seed=7)

    for r in (h, p, mc):
        assert r.cvar_loss is not None
        assert r.cvar_loss >= r.var_loss - 1e-9
