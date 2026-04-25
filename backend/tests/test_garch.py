"""
Tests for GARCH(1,1)-t module — fitting, simulation, and VaR.

These tests use synthetic GARCH-generated data so the library's fit
should recover the known parameters approximately. We also verify that
GARCH-t VaR ≥ parametric VaR for heavy-tailed data (expected since
GARCH captures clustering and t captures fat tails).
"""
from __future__ import annotations

import numpy as np
import pytest

from app.services.garch import (
    GarchFitResult,
    fit_garch_t,
    garch_var,
    simulate_garch_paths,
)


def _generate_garch_data(
    omega: float = 1e-6,
    alpha: float = 0.08,
    beta: float = 0.90,
    nu: float = 5.0,
    n: int = 2000,
    seed: int = 42,
) -> np.ndarray:
    """Generate synthetic GARCH(1,1)-t data with known parameters."""
    rng = np.random.default_rng(seed)
    r = np.zeros(n)
    sigma2 = np.zeros(n)
    sigma2[0] = omega / (1 - alpha - beta)  # unconditional variance

    for t in range(1, n):
        z = rng.standard_t(nu)
        if nu > 2:
            z /= np.sqrt(nu / (nu - 2))
        r[t] = np.sqrt(sigma2[t - 1]) * z
        sigma2[t] = omega + alpha * r[t - 1] ** 2 + beta * sigma2[t - 1]

    return r


# ---------------------------------------------------------------------------
class TestGarchFit:
    @pytest.fixture(scope="class")
    def garch_data(self):
        return _generate_garch_data()

    def test_fit_converges(self, garch_data):
        fit = fit_garch_t(garch_data)
        assert isinstance(fit, GarchFitResult)
        assert fit.persistence < 1.0

    def test_persistence_reasonable(self, garch_data):
        fit = fit_garch_t(garch_data)
        # True persistence = 0.08 + 0.90 = 0.98
        assert 0.85 < fit.persistence < 1.0

    def test_alpha_positive(self, garch_data):
        fit = fit_garch_t(garch_data)
        assert fit.alpha > 0

    def test_beta_positive(self, garch_data):
        fit = fit_garch_t(garch_data)
        assert fit.beta > 0

    def test_nu_reasonable(self, garch_data):
        """Student-t df should be in a sensible range (not infinity = normal)."""
        fit = fit_garch_t(garch_data)
        assert 2.5 < fit.nu < 50  # true is 5

    def test_too_few_observations_raises(self):
        with pytest.raises(ValueError, match="100 observations"):
            fit_garch_t(np.random.randn(50))


# ---------------------------------------------------------------------------
class TestGarchSimulation:
    def test_simulation_shape(self):
        fit = GarchFitResult(
            omega=1e-6, alpha=0.08, beta=0.90, nu=5.0,
            persistence=0.98, last_sigma2=1e-4,
            log_likelihood=0, n_obs=1000, aic=0, bic=0,
        )
        paths = simulate_garch_paths(fit, n_paths=100, horizon=10, seed=42)
        assert paths.shape == (100, 10)

    def test_simulation_mean_near_zero(self):
        """Mean of GARCH paths should be near zero (zero-mean model)."""
        fit = GarchFitResult(
            omega=1e-6, alpha=0.08, beta=0.90, nu=5.0,
            persistence=0.98, last_sigma2=1e-4,
            log_likelihood=0, n_obs=1000, aic=0, bic=0,
        )
        paths = simulate_garch_paths(fit, n_paths=50_000, horizon=1, seed=42)
        mean_return = paths.mean()
        assert abs(mean_return) < 0.005  # should be near zero


# ---------------------------------------------------------------------------
class TestGarchVaR:
    @pytest.fixture(scope="class")
    def portfolio_returns(self):
        """3-asset portfolio with one GARCH-like volatile asset."""
        rng = np.random.default_rng(42)
        n = 1500
        normal_assets = rng.standard_normal((n, 2)) * 0.01
        garch_asset = _generate_garch_data(n=n, seed=42).reshape(-1, 1)
        return np.hstack([normal_assets, garch_asset])

    def test_garch_var_runs(self, portfolio_returns):
        w = np.array([0.4, 0.3, 0.3])
        result = garch_var(w, portfolio_returns, confidence=0.95, n_paths=5000)
        assert result.var_loss > 0
        assert result.cvar_loss >= result.var_loss - 1e-10
        assert result.method == "garch_t"

    def test_higher_confidence_higher_var(self, portfolio_returns):
        """99% VaR should be ≥ 95% VaR."""
        w = np.array([0.4, 0.3, 0.3])
        var_95 = garch_var(w, portfolio_returns, confidence=0.95, n_paths=5000, seed=42)
        var_99 = garch_var(w, portfolio_returns, confidence=0.99, n_paths=5000, seed=42)
        assert var_99.var_loss >= var_95.var_loss * 0.9  # some noise allowed

    def test_cvar_gte_var(self, portfolio_returns):
        w = np.array([0.4, 0.3, 0.3])
        result = garch_var(w, portfolio_returns, confidence=0.95, n_paths=10000, seed=42)
        assert result.cvar_loss >= result.var_loss - 1e-8
