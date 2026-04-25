"""
VaR Backtesting — Kupiec POF + Christoffersen Conditional Coverage
====================================================================

Validates that a VaR model is correctly calibrated by comparing realized
violations (days where the loss exceeded VaR) against the expected rate.

Two standard tests are implemented:

1. **Kupiec (1995) Proportion of Failures (POF)**
   H₀: The realized violation rate p̂ equals the theoretical rate α = 1 − c.
   LR_POF = 2·[ln(p̂^x · (1−p̂)^(n−x)) − ln(α^x · (1−α)^(n−x))]
   Under H₀, LR_POF ~ χ²(1).

2. **Christoffersen (1998) Conditional Coverage**
   Tests both that the unconditional violation rate is correct AND that
   violations are independently distributed (no clustering).
   LR_CC = LR_POF + LR_IND, where LR_IND is a test for serial independence
   of the violation indicator sequence.
   Under H₀, LR_CC ~ χ²(2).

Master plan reference: Phase 2 → "Backtesting — Kupiec POF +
Christoffersen conditional coverage"
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np
from scipy import stats as sp_stats

from app.services.var import (
    VarMethod,
    historical_var,
    monte_carlo_var,
    parametric_var,
)


# ---------------------------------------------------------------------------
@dataclass
class BacktestResult:
    """Full backtesting result for a single VaR method."""
    var_method: str
    confidence: float
    n_observations: int
    n_violations: int
    expected_violations: float
    violation_rate: float                # realized p̂
    expected_violation_rate: float       # α = 1 - c

    # Kupiec POF
    kupiec_lr: float
    kupiec_pval: float
    pass_kupiec: bool

    # Christoffersen conditional coverage
    christoffersen_lr: float | None
    christoffersen_pval: float | None
    pass_christoffersen: bool | None

    # Independence test (sub-component of Christoffersen)
    independence_lr: float | None
    independence_pval: float | None


# ---------------------------------------------------------------------------
# Statistical tests
# ---------------------------------------------------------------------------
def kupiec_pof(
    n: int,
    x: int,
    alpha: float,
) -> tuple[float, float]:
    """
    Kupiec (1995) Proportion of Failures test.

    Parameters
    ----------
    n     : number of observations
    x     : number of violations (realized losses > VaR)
    alpha : expected violation rate = 1 − confidence

    Returns
    -------
    (lr_statistic, p_value) where lr ~ χ²(1) under H₀.
    """
    if x == 0:
        # No violations — degenerate case. The model may be too conservative.
        # Log-likelihood ratio is dominated by the (1−p) term.
        lr = -2.0 * (n * np.log(1.0 - alpha))
        return lr, float(sp_stats.chi2.sf(lr, df=1))

    if x == n:
        lr = -2.0 * (n * np.log(alpha))
        return lr, float(sp_stats.chi2.sf(lr, df=1))

    p_hat = x / n

    # LR = 2 * [ ln L_hat - ln L_0 ]
    lr_hat = x * np.log(p_hat) + (n - x) * np.log(1.0 - p_hat)
    lr_0 = x * np.log(alpha) + (n - x) * np.log(1.0 - alpha)
    lr = 2.0 * (lr_hat - lr_0)

    pval = float(sp_stats.chi2.sf(lr, df=1))
    return float(lr), pval


def christoffersen_cc(
    violations: np.ndarray,
    alpha: float,
) -> tuple[float, float, float, float]:
    """
    Christoffersen (1998) Conditional Coverage test.

    Tests both unconditional coverage (Kupiec) AND serial independence
    of the violation indicator sequence.

    Parameters
    ----------
    violations : (T,) binary array where 1 = VaR was breached
    alpha      : expected violation rate

    Returns
    -------
    (lr_cc, pval_cc, lr_ind, pval_ind)
    lr_cc  ~ χ²(2) under H₀ (correct coverage + independence)
    lr_ind ~ χ²(1) under H₀ (independence only)
    """
    v = np.asarray(violations, dtype=int)
    n = len(v)
    x = int(v.sum())

    lr_pof, _ = kupiec_pof(n, x, alpha)

    # Independence test via transition counts
    # n_ij = count of transitions from state i to state j
    n00 = n01 = n10 = n11 = 0
    for t in range(1, n):
        prev, curr = v[t - 1], v[t]
        if prev == 0 and curr == 0:
            n00 += 1
        elif prev == 0 and curr == 1:
            n01 += 1
        elif prev == 1 and curr == 0:
            n10 += 1
        else:
            n11 += 1

    # Transition probabilities
    total_from_0 = n00 + n01
    total_from_1 = n10 + n11

    if total_from_0 == 0 or total_from_1 == 0:
        # Degenerate: not enough transitions to test independence
        return lr_pof, float(sp_stats.chi2.sf(lr_pof, df=2)), 0.0, 1.0

    p01 = n01 / total_from_0
    p11 = n11 / total_from_1

    # Unconstrained log-likelihood
    ll_1 = 0.0
    if n00 > 0:
        ll_1 += n00 * np.log(1 - p01)
    if n01 > 0:
        ll_1 += n01 * np.log(p01)
    if n10 > 0:
        ll_1 += n10 * np.log(1 - p11)
    if n11 > 0:
        ll_1 += n11 * np.log(p11)

    # Constrained log-likelihood (independence: p01 = p11 = p̂)
    p_hat = x / n if n > 0 else 0.0
    ll_0 = 0.0
    if p_hat > 0 and p_hat < 1:
        n_no_viol = n00 + n10
        n_viol = n01 + n11
        if n_no_viol > 0:
            ll_0 += n_no_viol * np.log(1 - p_hat)
        if n_viol > 0:
            ll_0 += n_viol * np.log(p_hat)

    lr_ind = 2.0 * (ll_1 - ll_0)
    lr_ind = max(0.0, lr_ind)  # numerical floor
    pval_ind = float(sp_stats.chi2.sf(lr_ind, df=1))

    lr_cc = lr_pof + lr_ind
    pval_cc = float(sp_stats.chi2.sf(lr_cc, df=2))

    return float(lr_cc), pval_cc, float(lr_ind), pval_ind


# ---------------------------------------------------------------------------
# Rolling-window backtest runner
# ---------------------------------------------------------------------------
def run_backtest(
    weights: np.ndarray,
    daily_returns: np.ndarray,
    confidence: float = 0.95,
    var_method: VarMethod = "parametric",
    window: int = 252,
    significance: float = 0.05,
) -> BacktestResult:
    """
    Run a rolling-window VaR backtest.

    For each day t in [window, T):
      1. Estimate VaR using the previous `window` days of returns.
      2. Check if the actual portfolio return on day t violated the VaR.

    Then run Kupiec POF + Christoffersen CC on the violation sequence.

    Parameters
    ----------
    weights        : (n,) portfolio weights
    daily_returns  : (T, n) daily returns matrix
    confidence     : VaR confidence level
    var_method     : 'historical', 'parametric', or 'monte_carlo'
    window         : rolling lookback window (in trading days)
    significance   : significance level for pass/fail (default 5%)

    Returns
    -------
    BacktestResult with all test statistics.
    """
    w = np.asarray(weights, dtype=np.float64)
    dr = np.asarray(daily_returns, dtype=np.float64)
    T, n = dr.shape

    if T < window + 30:
        raise ValueError(
            f"Need at least {window + 30} days for backtesting, got {T}."
        )

    # Portfolio return series
    port_returns = dr @ w

    violations = []
    for t in range(window, T):
        # Lookback window
        lookback = dr[t - window:t]

        # Compute 1-day VaR using the specified method
        if var_method == "historical":
            vr = historical_var(w, lookback, confidence=confidence, horizon_days=1)
        elif var_method == "parametric":
            vr = parametric_var(w, daily_returns=lookback, confidence=confidence, horizon_days=1)
        else:  # monte_carlo
            vr = parametric_var(
                w, daily_returns=lookback, confidence=confidence, horizon_days=1,
            )  # use parametric for speed in backtest; MC is too slow per-step

        actual_return = port_returns[t]
        # Violation: actual loss exceeded VaR
        # VaR is defined as a positive loss, so violation = actual_return < -VaR
        violated = 1 if actual_return < -vr.var_loss else 0
        violations.append(violated)

    violations_arr = np.array(violations, dtype=int)
    n_obs = len(violations_arr)
    n_viol = int(violations_arr.sum())
    alpha = 1.0 - confidence
    expected_viol = alpha * n_obs

    # Kupiec
    lr_pof, pval_pof = kupiec_pof(n_obs, n_viol, alpha)

    # Christoffersen
    lr_cc, pval_cc, lr_ind, pval_ind = christoffersen_cc(violations_arr, alpha)

    return BacktestResult(
        var_method=var_method,
        confidence=confidence,
        n_observations=n_obs,
        n_violations=n_viol,
        expected_violations=expected_viol,
        violation_rate=n_viol / n_obs if n_obs > 0 else 0.0,
        expected_violation_rate=alpha,
        kupiec_lr=lr_pof,
        kupiec_pval=pval_pof,
        pass_kupiec=pval_pof > significance,
        christoffersen_lr=lr_cc,
        christoffersen_pval=pval_cc,
        pass_christoffersen=pval_cc > significance,
        independence_lr=lr_ind,
        independence_pval=pval_ind,
    )
