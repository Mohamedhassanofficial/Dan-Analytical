"""
GARCH(1,1)-t Value at Risk
===========================

Implements Monte Carlo VaR using GARCH(1,1) with Student-t innovations,
addressing the heavy-tailed returns observed in Tadawul equities that the
plain-normal Monte Carlo in var.py underestimates.

The GARCH(1,1) model:
    σ²_t = ω + α · ε²_{t-1} + β · σ²_{t-1}

With Student-t innovations:
    ε_t = σ_t · z_t,   z_t ~ t(ν)

This captures volatility clustering (high-vol days tend to follow high-vol
days) and fat tails — both well-documented properties of Tadawul returns.

Architecture
------------
- Uses the `arch` library for GARCH fitting (Kevin Sheppard's production-
  grade implementation, MIT license, ~15 MB). This is the gold standard
  for GARCH in Python and is used by hundreds of finance shops.
- Falls back to a simplified scipy MLE if `arch` is not installed.

Master plan reference: Phase 2 → "Monte Carlo (GARCH-t) at 95% and 99%"
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Literal

import numpy as np
from scipy import stats as sp_stats

from app.services.var import VarResult

log = logging.getLogger(__name__)

try:
    from arch import arch_model
    _HAS_ARCH = True
except ImportError:
    _HAS_ARCH = False
    arch_model = None  # type: ignore[assignment,misc]


# ---------------------------------------------------------------------------
# GARCH fit result
# ---------------------------------------------------------------------------
@dataclass
class GarchFitResult:
    """Parameters of a fitted GARCH(1,1)-t model."""
    omega: float       # constant in variance equation
    alpha: float       # ARCH coefficient (news impact)
    beta: float        # GARCH coefficient (persistence)
    nu: float          # degrees of freedom of Student-t innovations
    persistence: float  # α + β — should be < 1 for stationarity
    last_sigma2: float  # conditional variance at the last observation
    log_likelihood: float
    n_obs: int
    aic: float
    bic: float


# ---------------------------------------------------------------------------
# Fit GARCH(1,1)-t
# ---------------------------------------------------------------------------
def fit_garch_t(
    returns: np.ndarray,
    rescale: bool = True,
) -> GarchFitResult:
    """
    Fit a GARCH(1,1) model with Student-t innovations to a univariate
    return series.

    Parameters
    ----------
    returns : (T,) array of daily returns (log or simple).
    rescale : multiply returns by 100 before fitting (arch convention for
              numerical stability). Results are back-scaled internally.

    Returns
    -------
    GarchFitResult with estimated parameters.

    Raises
    ------
    RuntimeError if fitting fails.
    """
    r = np.asarray(returns, dtype=np.float64).ravel()
    if len(r) < 100:
        raise ValueError(
            f"GARCH fitting requires ≥100 observations, got {len(r)}."
        )

    if _HAS_ARCH:
        return _fit_arch_library(r, rescale)
    return _fit_scipy_fallback(r)


def _fit_arch_library(r: np.ndarray, rescale: bool) -> GarchFitResult:
    """Use Kevin Sheppard's arch library (production path)."""
    model = arch_model(
        r * (100.0 if rescale else 1.0),
        vol="GARCH",
        p=1,
        q=1,
        dist="t",         # Student-t innovations
        mean="Zero",       # assume zero-mean for daily returns
        rescale=False,     # we handle rescale ourselves
    )
    result = model.fit(disp="off", show_warning=False)

    scale_sq = 10000.0 if rescale else 1.0

    omega = float(result.params.get("omega", 0)) / scale_sq
    alpha = float(result.params.get("alpha[1]", 0))
    beta_param = float(result.params.get("beta[1]", 0))
    nu = float(result.params.get("nu", 5))

    cond_vol = result.conditional_volatility
    last_sigma2 = (float(cond_vol.iloc[-1]) ** 2) / scale_sq if len(cond_vol) > 0 else omega / (1 - alpha - beta_param)

    return GarchFitResult(
        omega=omega,
        alpha=alpha,
        beta=beta_param,
        nu=nu,
        persistence=alpha + beta_param,
        last_sigma2=last_sigma2,
        log_likelihood=float(result.loglikelihood),
        n_obs=int(result.nobs),
        aic=float(result.aic),
        bic=float(result.bic),
    )


def _fit_scipy_fallback(r: np.ndarray) -> GarchFitResult:
    """
    Simplified MLE fallback when arch is not installed.
    Fits GARCH(1,1) with normal innovations (not t — approximation).
    """
    from scipy.optimize import minimize as sp_minimize

    T = len(r)

    def neg_log_lik(params):
        omega, alpha, beta = params
        if omega <= 0 or alpha < 0 or beta < 0 or alpha + beta >= 1:
            return 1e12
        sigma2 = np.zeros(T)
        sigma2[0] = np.var(r)
        for t in range(1, T):
            sigma2[t] = omega + alpha * r[t - 1] ** 2 + beta * sigma2[t - 1]
            if sigma2[t] <= 0:
                return 1e12
        ll = -0.5 * np.sum(np.log(2 * np.pi * sigma2) + r ** 2 / sigma2)
        return -ll

    var_r = float(np.var(r))
    x0 = [var_r * 0.05, 0.08, 0.88]
    bounds = [(1e-10, None), (1e-6, 0.999), (1e-6, 0.999)]

    res = sp_minimize(neg_log_lik, x0, method="L-BFGS-B", bounds=bounds)

    omega, alpha, beta = res.x

    # Compute last conditional variance
    sigma2 = np.zeros(T)
    sigma2[0] = var_r
    for t in range(1, T):
        sigma2[t] = omega + alpha * r[t - 1] ** 2 + beta * sigma2[t - 1]

    return GarchFitResult(
        omega=omega,
        alpha=alpha,
        beta=beta,
        nu=5.0,  # default df for fallback
        persistence=alpha + beta,
        last_sigma2=float(sigma2[-1]),
        log_likelihood=-res.fun,
        n_obs=T,
        aic=2 * 3 + 2 * res.fun,  # 3 params
        bic=3 * np.log(T) + 2 * res.fun,
    )


# ---------------------------------------------------------------------------
# GARCH Monte Carlo path simulation
# ---------------------------------------------------------------------------
def simulate_garch_paths(
    fit: GarchFitResult,
    n_paths: int,
    horizon: int,
    seed: int | None = None,
) -> np.ndarray:
    """
    Simulate h-day return paths from a fitted GARCH(1,1)-t model.

    Each path starts from the last observed conditional variance and
    projects forward using the GARCH recursion with fresh t(ν) draws.

    Parameters
    ----------
    fit       : GarchFitResult from fit_garch_t
    n_paths   : number of Monte Carlo paths
    horizon   : number of days per path
    seed      : RNG seed for reproducibility

    Returns
    -------
    (n_paths, horizon) array of simulated daily returns.
    """
    rng = np.random.default_rng(seed)

    omega = fit.omega
    alpha = fit.alpha
    beta = fit.beta
    nu = fit.nu

    # Draw standardized innovations from Student-t(ν)
    # scipy's t distribution has variance ν/(ν-2), so standardize
    z = rng.standard_t(df=nu, size=(n_paths, horizon))
    if nu > 2:
        z = z / np.sqrt(nu / (nu - 2))  # standardize to unit variance

    returns = np.zeros((n_paths, horizon))
    sigma2 = np.full(n_paths, fit.last_sigma2)

    for t in range(horizon):
        returns[:, t] = np.sqrt(sigma2) * z[:, t]
        sigma2 = omega + alpha * returns[:, t] ** 2 + beta * sigma2

    return returns


# ---------------------------------------------------------------------------
# GARCH-t VaR
# ---------------------------------------------------------------------------
def garch_var(
    weights: np.ndarray,
    daily_returns: np.ndarray,
    confidence: float = 0.95,
    horizon_days: int = 1,
    n_paths: int = 10_000,
    seed: int | None = 42,
) -> VarResult:
    """
    Monte Carlo VaR using per-asset GARCH(1,1)-t models.

    For portfolios this fits GARCH to the portfolio return series
    (univariate approach — faster and more robust than n separate
    multivariate GARCH fits for n > 6).

    Parameters
    ----------
    weights        : (n,) portfolio weights
    daily_returns  : (T, n) daily returns matrix
    confidence     : VaR confidence level (0.95 or 0.99)
    horizon_days   : holding period in trading days
    n_paths        : number of Monte Carlo paths
    seed           : RNG seed

    Returns
    -------
    VarResult with method="garch_t"
    """
    w = np.asarray(weights, dtype=np.float64)
    dr = np.asarray(daily_returns, dtype=np.float64)

    if dr.ndim != 2 or dr.shape[1] != len(w):
        raise ValueError(f"daily_returns must be (T, {len(w)}), got {dr.shape}")

    # Portfolio return series
    port_returns = dr @ w
    mu_p = float(np.mean(port_returns))
    sigma_p = float(np.std(port_returns, ddof=0))

    # Fit GARCH to portfolio returns
    fit = fit_garch_t(port_returns)

    # Simulate forward paths
    sim_returns = simulate_garch_paths(fit, n_paths, horizon_days, seed)

    # h-day cumulative returns
    cum_returns = sim_returns.sum(axis=1)  # sum of daily returns over horizon

    # VaR = negative quantile of the loss distribution
    q = 1.0 - confidence
    loss_cut = float(np.quantile(cum_returns, q))
    var_loss = max(0.0, -loss_cut)

    # CVaR: mean of returns worse than the VaR cutoff
    worse = cum_returns[cum_returns <= loss_cut]
    cvar_loss = float(-worse.mean()) if worse.size > 0 else var_loss

    return VarResult(
        method="garch_t",
        confidence=confidence,
        horizon_days=horizon_days,
        var_loss=var_loss,
        cvar_loss=cvar_loss,
        portfolio_mean_daily=mu_p,
        portfolio_vol_daily=sigma_p,
        simulated_paths=n_paths,
    )


# ---------------------------------------------------------------------------
# Basel FRTB Expected Shortfall at 97.5%
# ---------------------------------------------------------------------------
def frtb_expected_shortfall(
    weights: np.ndarray,
    daily_returns: np.ndarray,
    horizon_days: int = 10,
    n_paths: int = 50_000,
    seed: int | None = 42,
) -> dict:
    """
    Basel III FRTB Expected Shortfall at 97.5% confidence over a
    10-day horizon, using GARCH-t simulation.

    Returns dict with es_975, var_975, and garch_fit metadata.
    """
    result = garch_var(
        weights, daily_returns,
        confidence=0.975,
        horizon_days=horizon_days,
        n_paths=n_paths,
        seed=seed,
    )

    w = np.asarray(weights, dtype=np.float64)
    port_returns = np.asarray(daily_returns, dtype=np.float64) @ w
    fit = fit_garch_t(port_returns)

    return {
        "es_975": result.cvar_loss,
        "var_975": result.var_loss,
        "horizon_days": horizon_days,
        "confidence": 0.975,
        "garch_params": {
            "omega": fit.omega,
            "alpha": fit.alpha,
            "beta": fit.beta,
            "nu": fit.nu,
            "persistence": fit.persistence,
        },
        "n_paths": n_paths,
    }
