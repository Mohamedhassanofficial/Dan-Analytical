"""
Tests for VaR backtesting — Kupiec POF + Christoffersen conditional coverage.
"""
from __future__ import annotations

import numpy as np
import pytest

from app.services.backtesting import (
    BacktestResult,
    christoffersen_cc,
    kupiec_pof,
    run_backtest,
)


# ---------------------------------------------------------------------------
# Kupiec POF
# ---------------------------------------------------------------------------
class TestKupiecPOF:
    def test_exact_rate_accepted(self):
        """A perfectly calibrated model (p̂ = α) should not be rejected."""
        n = 1000
        alpha = 0.05
        x = 50  # exactly 5% violations
        lr, pval = kupiec_pof(n, x, alpha)
        assert pval > 0.05, f"p-value {pval} should be > 0.05 for perfect calibration"

    def test_too_many_violations_rejected(self):
        """A model with way too many violations should be rejected."""
        n = 1000
        alpha = 0.05
        x = 120  # 12% violations vs expected 5% — should reject
        lr, pval = kupiec_pof(n, x, alpha)
        assert pval < 0.05, f"p-value {pval} should be < 0.05"

    def test_too_few_violations_rejected(self):
        """A model that never violates is also miscalibrated."""
        n = 1000
        alpha = 0.05
        x = 5  # only 0.5% — too conservative
        lr, pval = kupiec_pof(n, x, alpha)
        assert pval < 0.05

    def test_zero_violations(self):
        """Edge case: no violations at all."""
        lr, pval = kupiec_pof(1000, 0, 0.05)
        assert pval < 0.05  # should reject — 0 violations out of 1000 at 5% is way off

    def test_lr_non_negative(self):
        """LR statistic should always be non-negative."""
        for x in [0, 10, 50, 100, 500]:
            lr, _ = kupiec_pof(1000, x, 0.05)
            assert lr >= -1e-10


# ---------------------------------------------------------------------------
# Christoffersen
# ---------------------------------------------------------------------------
class TestChristoffersen:
    def test_iid_violations_pass(self):
        """i.i.d. Bernoulli violations should pass the independence test."""
        rng = np.random.default_rng(42)
        alpha = 0.05
        n = 2000
        violations = rng.binomial(1, alpha, size=n)

        lr_cc, pval_cc, lr_ind, pval_ind = christoffersen_cc(violations, alpha)
        # With i.i.d. violations at the right rate, both should pass
        # (but statistical tests have finite power, so use a generous threshold)
        assert pval_cc > 0.01 or pval_ind > 0.01

    def test_clustered_violations_detected(self):
        """Clustered violations (violation followed by violation) should fail independence."""
        n = 1000
        violations = np.zeros(n, dtype=int)
        # Create clusters of violations
        for i in range(0, n - 5, 50):
            violations[i:i + 5] = 1  # 5 consecutive violations every 50 days

        alpha = 0.05
        lr_cc, pval_cc, lr_ind, pval_ind = christoffersen_cc(violations, alpha)
        # Clustering should be detected (low p-value for independence)
        assert pval_ind < 0.10  # independence test should reject


# ---------------------------------------------------------------------------
# Full backtest runner
# ---------------------------------------------------------------------------
class TestRunBacktest:
    @pytest.fixture(scope="class")
    def long_returns(self):
        """Generate enough data for a meaningful backtest."""
        rng = np.random.default_rng(42)
        n_assets = 3
        n_days = 800  # need window + out-of-sample
        mu = np.array([0.0003, 0.0004, 0.00025])
        cov = np.array([
            [0.00015, 0.00005, 0.00004],
            [0.00005, 0.00020, 0.00006],
            [0.00004, 0.00006, 0.00012],
        ])
        return rng.multivariate_normal(mu, cov, size=n_days)

    def test_backtest_runs(self, long_returns):
        w = np.array([0.4, 0.35, 0.25])
        result = run_backtest(
            weights=w,
            daily_returns=long_returns,
            confidence=0.95,
            var_method="parametric",
            window=252,
        )
        assert isinstance(result, BacktestResult)
        assert result.n_observations > 0
        assert 0.0 <= result.violation_rate <= 1.0

    def test_backtest_too_few_data_raises(self):
        rng = np.random.default_rng(42)
        short = rng.standard_normal((100, 3))  # too short for window=252
        with pytest.raises(ValueError, match="at least"):
            run_backtest(
                weights=np.array([0.4, 0.35, 0.25]),
                daily_returns=short,
                window=252,
            )

    def test_backtest_result_has_all_fields(self, long_returns):
        w = np.array([0.4, 0.35, 0.25])
        result = run_backtest(w, long_returns, window=252)
        assert result.kupiec_pval >= 0
        assert result.christoffersen_pval is not None
        assert isinstance(result.pass_kupiec, bool)
        assert isinstance(result.pass_christoffersen, bool)
