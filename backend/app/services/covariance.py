"""
Covariance & Correlation Quality Utilities
===========================================

Provides:
  1. Ledoit-Wolf shrinkage (Oracle-Approximating Shrinkage, 2004 analytical
     formula — implemented manually so we don't need scikit-learn).
  2. Pearson Formula 2 correlation cross-check (Investment Details!AI28:AN34).
  3. Covariance quality report (eigenvalue spectrum, condition number, PSD).
  4. Nearest-PSD projection for numerical stability.

Excel parity targets (from excel_to_code_mapping.md):
  - Correlation: Investment Details!AI20:AN26 (CORREL) + AI28:AN34 (Formula 2)
  - Covariance: Optimal Portflio!R6:W11 (COVAR, ddof=0)
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np


# ---------------------------------------------------------------------------
# Ledoit-Wolf 2004 analytical shrinkage
# ---------------------------------------------------------------------------
def ledoit_wolf_shrinkage(
    returns: np.ndarray,
) -> tuple[np.ndarray, float]:
    """
    Compute the Ledoit-Wolf (2004) shrinkage estimator for the covariance
    matrix, targeting the scaled identity matrix (constant correlation model).

    This is the analytical oracle-approximating formula from:
        Ledoit & Wolf, "A well-conditioned estimator for large-dimensional
        covariance matrices", Journal of Multivariate Analysis, 2004.

    Parameters
    ----------
    returns : (T, n) array of centered or raw returns.
              If raw, they are demeaned internally.

    Returns
    -------
    cov_shrunk : (n, n) shrunk covariance matrix
    shrinkage  : optimal shrinkage intensity δ* ∈ [0, 1]
    """
    X = np.asarray(returns, dtype=np.float64)
    T, n = X.shape

    # Demean
    X = X - X.mean(axis=0, keepdims=True)

    # Sample covariance (population, ddof=0 to match Excel COVAR)
    S = (X.T @ X) / T

    # Shrinkage target: scaled identity μI where μ = trace(S)/n
    mu = np.trace(S) / n
    F = mu * np.eye(n)

    # Compute δ* analytically (Ledoit-Wolf Eq. 2)
    # δ² = Σ_ij [ Var(s_ij) ] / || S - F ||²_F
    # where Var(s_ij) is estimated from the sample fourth moments.

    # Squared Frobenius norm of S - F
    delta = S - F
    norm_sq = np.sum(delta ** 2)

    if norm_sq < 1e-16:
        return S.copy(), 0.0  # S is already proportional to identity

    # Estimate sum of asymptotic variances of s_ij
    # Using the formula: (1/T²) Σ_k Σ_ij (x_ki·x_kj - s_ij)²
    X2 = X ** 2
    # sum of squared (outer products - sample cov) over all samples
    phi_sum = 0.0
    for k in range(T):
        outer_k = np.outer(X[k], X[k])
        phi_sum += np.sum((outer_k - S) ** 2)
    phi = phi_sum / (T ** 2)

    # Optimal shrinkage intensity
    shrinkage = float(np.clip(phi / norm_sq, 0.0, 1.0))

    cov_shrunk = shrinkage * F + (1.0 - shrinkage) * S
    return cov_shrunk, shrinkage


def ledoit_wolf_shrinkage_fast(
    returns: np.ndarray,
) -> tuple[np.ndarray, float]:
    """
    Vectorized Ledoit-Wolf — avoids the Python loop over T samples.
    This is the production-grade version for large T.
    """
    X = np.asarray(returns, dtype=np.float64)
    T, n = X.shape

    X = X - X.mean(axis=0, keepdims=True)
    S = (X.T @ X) / T

    mu = np.trace(S) / n
    delta = S - mu * np.eye(n)
    norm_sq = np.sum(delta ** 2)

    if norm_sq < 1e-16:
        return S.copy(), 0.0

    # Vectorized phi computation: E[(x_k x_k' - S)^2]
    # = (1/T²) sum_k || x_k x_k' - S ||²_F
    # = (1/T²) [ sum_k ||x_k x_k'||² - 2·sum_k tr(x_k x_k' S) + T·||S||² ]
    # = (1/T²) [ sum_k (x_k'x_k)² - 2·sum_k (x_k' S x_k) + T·||S||² ]

    X_sq_norms = np.sum(X ** 2, axis=1)  # (T,) — ||x_k||²
    term1 = np.sum(X_sq_norms ** 2)  # sum (x_k'x_k)²

    SX = X @ S  # (T, n)
    term2 = 2.0 * np.sum(SX * X)   # 2 · sum_k x_k' S x_k

    term3 = T * np.sum(S ** 2)

    phi = (term1 - term2 + term3) / (T ** 2)

    shrinkage = float(np.clip(phi / norm_sq, 0.0, 1.0))
    cov_shrunk = shrinkage * mu * np.eye(n) + (1.0 - shrinkage) * S
    return cov_shrunk, shrinkage


# ---------------------------------------------------------------------------
# Correlation matrix — Pearson Formula 2
# ---------------------------------------------------------------------------
def correlation_from_covariance(cov: np.ndarray) -> np.ndarray:
    """
    Pearson Formula 2: corr[i,j] = cov[i,j] / (σ_i × σ_j).

    Matches Excel Investment Details!AI28:AN34 — the explicit long-hand
    formula that exists alongside CORREL() for verification.
    """
    cov = np.asarray(cov, dtype=np.float64)
    sd = np.sqrt(np.diag(cov))
    sd = np.where(sd < 1e-16, 1e-16, sd)  # avoid /0
    outer_sd = np.outer(sd, sd)
    return cov / outer_sd


def validate_correlation_parity(
    returns: np.ndarray,
    cov: np.ndarray,
    atol: float = 1e-10,
) -> dict:
    """
    Cross-check Pearson Formula 2 against np.corrcoef — both are
    mathematically identical but computed differently. This QA check
    guarantees we haven't introduced numerical drift.

    Returns a dict with max deviation and pass/fail flag.
    """
    corr_f2 = correlation_from_covariance(cov)
    corr_np = np.corrcoef(returns, rowvar=False)

    diff = np.abs(corr_f2 - corr_np)
    max_diff = float(np.max(diff))

    return {
        "formula2_vs_corrcoef_max_diff": max_diff,
        "parity_pass": max_diff < atol,
        "atol_used": atol,
    }


# ---------------------------------------------------------------------------
# Covariance quality report
# ---------------------------------------------------------------------------
@dataclass
class CovarianceQuality:
    n: int
    is_psd: bool
    min_eigenvalue: float
    max_eigenvalue: float
    condition_number: float
    trace: float
    determinant_log: float       # log(det) to avoid overflow
    suggested_shrinkage: float   # 0 if excellent, >0 if ill-conditioned
    eigenvalue_spectrum: list[float]


def covariance_quality_report(cov: np.ndarray) -> CovarianceQuality:
    """
    Diagnose the health of a covariance matrix. Useful for the admin
    dashboard and for detecting data quality issues before optimization.
    """
    cov = np.asarray(cov, dtype=np.float64)
    n = cov.shape[0]

    eigvals = np.linalg.eigvalsh(cov)  # real eigenvalues, ascending
    min_eig = float(eigvals[0])
    max_eig = float(eigvals[-1])

    is_psd = min_eig >= -1e-10
    cond = max_eig / max(abs(min_eig), 1e-16) if min_eig > 0 else float("inf")

    # Log-determinant via sum of log eigenvalues (avoids overflow)
    pos_eigvals = eigvals[eigvals > 0]
    log_det = float(np.sum(np.log(pos_eigvals))) if len(pos_eigvals) > 0 else -float("inf")

    # Suggest shrinkage if condition number is bad (>1000) or non-PSD
    suggested = 0.0
    if not is_psd:
        suggested = 0.5
    elif cond > 1000:
        suggested = min(1.0, cond / 10000)

    return CovarianceQuality(
        n=n,
        is_psd=is_psd,
        min_eigenvalue=min_eig,
        max_eigenvalue=max_eig,
        condition_number=cond,
        trace=float(np.trace(cov)),
        determinant_log=log_det,
        suggested_shrinkage=suggested,
        eigenvalue_spectrum=eigvals.tolist(),
    )


# ---------------------------------------------------------------------------
# Nearest PSD projection (Higham, 2002)
# ---------------------------------------------------------------------------
def nearest_psd(cov: np.ndarray, eps: float = 1e-10) -> np.ndarray:
    """
    Project a symmetric matrix to the nearest positive semi-definite matrix
    by clipping negative eigenvalues to eps. Preserves the diagonal as closely
    as possible. Used as a fallback when the sample covariance is numerically
    non-PSD for large n.
    """
    cov = np.asarray(cov, dtype=np.float64)
    eigvals, eigvecs = np.linalg.eigh(cov)
    eigvals = np.maximum(eigvals, eps)
    return eigvecs @ np.diag(eigvals) @ eigvecs.T


# ---------------------------------------------------------------------------
# Dispatch: choose covariance method
# ---------------------------------------------------------------------------
CovMethod = Literal["raw", "ledoit_wolf"]


def compute_covariance(
    returns: np.ndarray,
    method: CovMethod = "raw",
) -> tuple[np.ndarray, dict]:
    """
    Compute covariance matrix using the specified method.

    Returns (cov_matrix, metadata_dict).
    """
    returns = np.asarray(returns, dtype=np.float64)

    if method == "ledoit_wolf":
        cov, shrinkage = ledoit_wolf_shrinkage_fast(returns)
        quality = covariance_quality_report(cov)
        return cov, {
            "method": "ledoit_wolf",
            "shrinkage_intensity": shrinkage,
            "condition_number": quality.condition_number,
            "is_psd": quality.is_psd,
        }
    else:
        # Raw population covariance (ddof=0) — matches Excel COVAR
        cov = np.cov(returns, rowvar=False, ddof=0)
        quality = covariance_quality_report(cov)
        return cov, {
            "method": "raw (ddof=0, Excel COVAR parity)",
            "condition_number": quality.condition_number,
            "is_psd": quality.is_psd,
        }
