"""
Value at Risk (VaR) — three methods covering the Excel workbook's
`VaR (1..6)` sheets and the PDF's "tracking VaR" dashboard requirement.

Definitions
-----------
VaR at confidence level c over horizon h days = the loss L such that
P(loss > L) = 1 - c. By convention we return a POSITIVE number (the loss
magnitude) and label it in decimal form (0.025 = 2.5% of portfolio value).

CVaR (Conditional VaR / Expected Shortfall) is the mean loss beyond VaR,
useful for heavy-tailed distributions. We return it alongside.

Methods
-------
1. Historical  — empirical quantile of the observed daily portfolio returns,
                 scaled by sqrt(h). No distributional assumption.
2. Parametric  — assume normal; VaR = -(μ_p*h - z·σ_p·sqrt(h))
                 where z = Φ⁻¹(1-c). Excel slide pattern, fastest.
3. Monte Carlo — simulate h-day paths from N(μ_daily, Σ_daily) and take
                 empirical quantile. Robust for non-normal inputs when
                 Σ is decent but μ has tail risk. Default N=10000 paths.

All functions take the portfolio weight vector w and either:
    - `daily_returns` (T x n matrix) for historical / any method, OR
    - `cov_daily` + `mu_daily` for parametric / Monte-Carlo when the caller
      has already precomputed statistics.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np
from scipy import stats

VarMethod = Literal["historical", "parametric", "monte_carlo"]


@dataclass
class VarResult:
    method: VarMethod
    confidence: float                # e.g. 0.95
    horizon_days: int                # e.g. 1 or 10
    var_loss: float                  # positive decimal fraction (loss)
    cvar_loss: float | None          # expected shortfall; None if not available
    portfolio_mean_daily: float
    portfolio_vol_daily: float
    simulated_paths: int | None = None   # only for monte_carlo


# ---------------------------------------------------------------------------
def _portfolio_stats(
    w: np.ndarray,
    mu_daily: np.ndarray | None,
    cov_daily: np.ndarray | None,
    daily_returns: np.ndarray | None,
) -> tuple[float, float, np.ndarray | None]:
    """Return (μ_p_daily, σ_p_daily, portfolio_daily_returns_or_None)."""
    w = np.asarray(w, dtype=float)

    if daily_returns is not None:
        dr = np.asarray(daily_returns, dtype=float)
        if dr.ndim != 2 or dr.shape[1] != len(w):
            raise ValueError(f"daily_returns must be (T, {len(w)})")
        port_daily = dr @ w
        mu_p = float(np.mean(port_daily))
        sigma_p = float(np.std(port_daily, ddof=0))
        return mu_p, sigma_p, port_daily

    if mu_daily is None or cov_daily is None:
        raise ValueError("Either daily_returns or both mu_daily + cov_daily required.")

    mu_daily = np.asarray(mu_daily, dtype=float)
    cov_daily = np.asarray(cov_daily, dtype=float)
    mu_p = float(w @ mu_daily)
    sigma_p = float(np.sqrt(w @ cov_daily @ w))
    return mu_p, sigma_p, None


# ---------------------------------------------------------------------------
def historical_var(
    weights: np.ndarray,
    daily_returns: np.ndarray,
    confidence: float = 0.95,
    horizon_days: int = 1,
) -> VarResult:
    """
    Empirical VaR from historical daily portfolio returns. Uses the
    (1-c) quantile of the return distribution; scales by sqrt(h) for
    multi-day horizons under the i.i.d. assumption.
    """
    mu_p, sigma_p, port_daily = _portfolio_stats(
        weights, None, None, daily_returns
    )
    assert port_daily is not None  # _portfolio_stats returns it for historical

    q = 1.0 - confidence
    # Numpy's quantile for the lower tail
    loss_cut = float(np.quantile(port_daily, q))
    var_1d = max(0.0, -loss_cut)
    # Expected shortfall: mean of returns worse than the cutoff
    worse_mask = port_daily <= loss_cut
    cvar_1d = (
        float(-np.mean(port_daily[worse_mask])) if worse_mask.any() else var_1d
    )

    scale = np.sqrt(horizon_days)
    return VarResult(
        method="historical",
        confidence=confidence,
        horizon_days=horizon_days,
        var_loss=var_1d * scale,
        cvar_loss=cvar_1d * scale,
        portfolio_mean_daily=mu_p,
        portfolio_vol_daily=sigma_p,
    )


def parametric_var(
    weights: np.ndarray,
    cov_daily: np.ndarray | None = None,
    mu_daily: np.ndarray | None = None,
    daily_returns: np.ndarray | None = None,
    confidence: float = 0.95,
    horizon_days: int = 1,
) -> VarResult:
    """
    Normal-distribution VaR: VaR = -(μ_p·h − z·σ_p·sqrt(h))
    CVaR = (μ_p·h − σ_p·sqrt(h)·φ(z)/(1-c))
    """
    mu_p, sigma_p, _ = _portfolio_stats(weights, mu_daily, cov_daily, daily_returns)

    z = stats.norm.ppf(1.0 - confidence)  # negative for lower tail
    mu_h = mu_p * horizon_days
    sigma_h = sigma_p * np.sqrt(horizon_days)

    var = float(-(mu_h + z * sigma_h))  # +z since z is negative, flip sign → loss
    # Expected shortfall under normality
    phi_z = stats.norm.pdf(z)
    cvar = float(-(mu_h - sigma_h * phi_z / (1.0 - confidence)))

    return VarResult(
        method="parametric",
        confidence=confidence,
        horizon_days=horizon_days,
        var_loss=max(0.0, var),
        cvar_loss=max(0.0, cvar),
        portfolio_mean_daily=mu_p,
        portfolio_vol_daily=sigma_p,
    )


def monte_carlo_var(
    weights: np.ndarray,
    cov_daily: np.ndarray | None = None,
    mu_daily: np.ndarray | None = None,
    daily_returns: np.ndarray | None = None,
    confidence: float = 0.95,
    horizon_days: int = 1,
    n_paths: int = 10_000,
    seed: int | None = None,
) -> VarResult:
    """
    Monte-Carlo VaR: simulate n_paths h-day portfolio returns from a
    multivariate normal fit to the provided stats, then take the empirical
    quantile. Good stress test for the parametric assumption.
    """
    w = np.asarray(weights, dtype=float)

    if daily_returns is not None:
        dr = np.asarray(daily_returns, dtype=float)
        mu_vec = dr.mean(axis=0)
        cov_mat = np.cov(dr, rowvar=False, ddof=0)
    elif mu_daily is not None and cov_daily is not None:
        mu_vec = np.asarray(mu_daily, dtype=float)
        cov_mat = np.asarray(cov_daily, dtype=float)
    else:
        raise ValueError("Provide daily_returns or both mu_daily + cov_daily.")

    rng = np.random.default_rng(seed)
    # Sum of h i.i.d. multivariate-normal draws = one draw with mean h·μ, cov h·Σ
    sim_mu = mu_vec * horizon_days
    sim_cov = cov_mat * horizon_days
    try:
        samples = rng.multivariate_normal(
            sim_mu, sim_cov, size=n_paths, check_valid="warn"
        )
    except np.linalg.LinAlgError:
        # Non-PSD (numerical) — project to nearest PSD by clipping eigenvalues
        eigvals, eigvecs = np.linalg.eigh(sim_cov)
        eigvals = np.clip(eigvals, 1e-12, None)
        sim_cov = eigvecs @ np.diag(eigvals) @ eigvecs.T
        samples = rng.multivariate_normal(sim_mu, sim_cov, size=n_paths)

    port_returns = samples @ w
    q = 1.0 - confidence
    loss_cut = float(np.quantile(port_returns, q))
    var = max(0.0, -loss_cut)
    worse = port_returns[port_returns <= loss_cut]
    cvar = float(-worse.mean()) if worse.size else var

    # For reporting, compute 1-day stats from inputs
    mu_p_daily = float(w @ mu_vec)
    sigma_p_daily = float(np.sqrt(w @ cov_mat @ w))

    return VarResult(
        method="monte_carlo",
        confidence=confidence,
        horizon_days=horizon_days,
        var_loss=var,
        cvar_loss=max(0.0, cvar),
        portfolio_mean_daily=mu_p_daily,
        portfolio_vol_daily=sigma_p_daily,
        simulated_paths=n_paths,
    )


# ---------------------------------------------------------------------------
def compute_all(
    weights: np.ndarray,
    daily_returns: np.ndarray,
    confidence: float = 0.95,
    horizon_days: int = 1,
    n_paths: int = 10_000,
    seed: int | None = 42,
    include_garch: bool = False,
) -> dict[str, VarResult]:
    """
    Compute VaR using all available methods in one call.

    The first three (historical, parametric, monte_carlo) are always computed.
    GARCH-t is optional (slower due to MLE fitting + simulation) and requires
    ≥100 observations.
    """
    h = historical_var(weights, daily_returns, confidence, horizon_days)
    p = parametric_var(
        weights, daily_returns=daily_returns,
        confidence=confidence, horizon_days=horizon_days,
    )
    mc = monte_carlo_var(
        weights, daily_returns=daily_returns,
        confidence=confidence, horizon_days=horizon_days,
        n_paths=n_paths, seed=seed,
    )
    result = {"historical": h, "parametric": p, "monte_carlo": mc}

    if include_garch:
        try:
            from app.services.garch import garch_var
            gt = garch_var(
                weights, daily_returns,
                confidence=confidence, horizon_days=horizon_days,
                n_paths=n_paths, seed=seed,
            )
            result["garch_t"] = gt
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning(
                "GARCH-t VaR failed (falling back to 3 methods): %s", exc
            )

    return result


def compute_frtb_es(
    weights: np.ndarray,
    daily_returns: np.ndarray,
    horizon_days: int = 10,
    n_paths: int = 50_000,
    seed: int | None = 42,
) -> dict:
    """
    Basel III FRTB Expected Shortfall at 97.5% confidence.

    Convenience wrapper that returns ES via GARCH-t (preferred) with
    parametric CVaR fallback.
    """
    try:
        from app.services.garch import frtb_expected_shortfall
        return frtb_expected_shortfall(
            weights, daily_returns,
            horizon_days=horizon_days,
            n_paths=n_paths, seed=seed,
        )
    except Exception:
        # Fallback to parametric CVaR at 97.5%
        vr = parametric_var(
            weights, daily_returns=daily_returns,
            confidence=0.975, horizon_days=horizon_days,
        )
        return {
            "es_975": float(vr.cvar_loss) if vr.cvar_loss else 0.0,
            "var_975": float(vr.var_loss),
            "horizon_days": horizon_days,
            "confidence": 0.975,
            "garch_params": None,
            "n_paths": 0,
            "fallback": "parametric (arch library unavailable)",
        }
