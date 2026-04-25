"""
Tests for covariance utilities — Ledoit-Wolf, Formula 2 correlation, quality report.
"""
from __future__ import annotations

import numpy as np
import pytest

from app.services.covariance import (
    CovarianceQuality,
    correlation_from_covariance,
    covariance_quality_report,
    ledoit_wolf_shrinkage_fast,
    nearest_psd,
    validate_correlation_parity,
)


@pytest.fixture(scope="module")
def normal_returns() -> np.ndarray:
    rng = np.random.default_rng(42)
    n_assets = 5
    n_days = 1000
    mu = np.array([0.0003, 0.0004, 0.00025, 0.0002, 0.00035])
    cov = np.array([
        [0.00020, 0.00005, 0.00004, 0.00003, 0.00006],
        [0.00005, 0.00025, 0.00006, 0.00004, 0.00007],
        [0.00004, 0.00006, 0.00015, 0.00003, 0.00005],
        [0.00003, 0.00004, 0.00003, 0.00018, 0.00004],
        [0.00006, 0.00007, 0.00005, 0.00004, 0.00022],
    ])
    return rng.multivariate_normal(mu, cov, size=n_days)


# ---------------------------------------------------------------------------
# Ledoit-Wolf
# ---------------------------------------------------------------------------
class TestLedoitWolf:
    def test_shrinkage_reduces_condition_number(self, normal_returns):
        raw_cov = np.cov(normal_returns, rowvar=False, ddof=0)
        shrunk_cov, shrinkage = ledoit_wolf_shrinkage_fast(normal_returns)

        raw_eigvals = np.linalg.eigvalsh(raw_cov)
        shrunk_eigvals = np.linalg.eigvalsh(shrunk_cov)

        raw_cond = raw_eigvals[-1] / raw_eigvals[0]
        shrunk_cond = shrunk_eigvals[-1] / shrunk_eigvals[0]

        assert shrunk_cond <= raw_cond + 1e-6

    def test_shrinkage_intensity_in_bounds(self, normal_returns):
        _, shrinkage = ledoit_wolf_shrinkage_fast(normal_returns)
        assert 0.0 <= shrinkage <= 1.0

    def test_shrunk_matrix_is_psd(self, normal_returns):
        shrunk_cov, _ = ledoit_wolf_shrinkage_fast(normal_returns)
        eigvals = np.linalg.eigvalsh(shrunk_cov)
        assert np.all(eigvals >= -1e-10)

    def test_shrunk_preserves_shape(self, normal_returns):
        shrunk_cov, _ = ledoit_wolf_shrinkage_fast(normal_returns)
        assert shrunk_cov.shape == (5, 5)

    def test_shrunk_is_symmetric(self, normal_returns):
        shrunk_cov, _ = ledoit_wolf_shrinkage_fast(normal_returns)
        assert np.allclose(shrunk_cov, shrunk_cov.T)


# ---------------------------------------------------------------------------
# Correlation Formula 2
# ---------------------------------------------------------------------------
class TestCorrelationFormula2:
    def test_formula2_matches_corrcoef(self, normal_returns):
        """Key parity check: Pearson Formula 2 vs np.corrcoef should match to 1e-10."""
        cov = np.cov(normal_returns, rowvar=False, ddof=0)
        parity = validate_correlation_parity(normal_returns, cov, atol=1e-10)
        assert parity["parity_pass"], f"max diff = {parity['formula2_vs_corrcoef_max_diff']}"

    def test_diagonal_is_ones(self, normal_returns):
        cov = np.cov(normal_returns, rowvar=False, ddof=0)
        corr = correlation_from_covariance(cov)
        assert np.allclose(np.diag(corr), 1.0)

    def test_values_in_range(self, normal_returns):
        cov = np.cov(normal_returns, rowvar=False, ddof=0)
        corr = correlation_from_covariance(cov)
        assert np.all(corr >= -1.0 - 1e-10)
        assert np.all(corr <= 1.0 + 1e-10)

    def test_symmetric(self, normal_returns):
        cov = np.cov(normal_returns, rowvar=False, ddof=0)
        corr = correlation_from_covariance(cov)
        assert np.allclose(corr, corr.T)


# ---------------------------------------------------------------------------
# Covariance Quality Report
# ---------------------------------------------------------------------------
class TestCovarianceQuality:
    def test_psd_matrix_detected(self, normal_returns):
        cov = np.cov(normal_returns, rowvar=False, ddof=0)
        report = covariance_quality_report(cov)
        assert report.is_psd
        assert report.min_eigenvalue >= -1e-10

    def test_non_psd_detected(self):
        bad_cov = np.array([
            [1.0, 1.5],
            [1.5, 1.0],
        ])  # eigenvalues: -0.5, 2.5 — not PSD
        report = covariance_quality_report(bad_cov)
        assert not report.is_psd
        assert report.min_eigenvalue < 0

    def test_condition_number_positive(self, normal_returns):
        cov = np.cov(normal_returns, rowvar=False, ddof=0)
        report = covariance_quality_report(cov)
        assert report.condition_number > 1.0

    def test_eigenvalue_spectrum_length(self, normal_returns):
        cov = np.cov(normal_returns, rowvar=False, ddof=0)
        report = covariance_quality_report(cov)
        assert len(report.eigenvalue_spectrum) == 5


# ---------------------------------------------------------------------------
# Nearest PSD
# ---------------------------------------------------------------------------
class TestNearestPSD:
    def test_projects_non_psd(self):
        bad_cov = np.array([
            [1.0, 1.5],
            [1.5, 1.0],
        ])
        fixed = nearest_psd(bad_cov)
        eigvals = np.linalg.eigvalsh(fixed)
        assert np.all(eigvals >= 0)

    def test_keeps_psd_unchanged(self, normal_returns):
        cov = np.cov(normal_returns, rowvar=False, ddof=0)
        fixed = nearest_psd(cov)
        assert np.allclose(cov, fixed, atol=1e-8)
