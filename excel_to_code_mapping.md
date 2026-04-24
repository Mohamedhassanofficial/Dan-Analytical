# Excel → Python Mapping for the Tadawul Portfolio Optimizer

A cell-by-cell map so any developer can verify the code reproduces every
formula in the workbook. All references are to
**Portflio_Optimization_Tadawul_ver_final_vertest3mohd.xlsm**.

## Slide 123 — Sharpe Ratio

| Excel | Formula | Python |
|---|---|---|
| `Optimal Portflio!J1` | `=B9*D2+D3*C9+D4*D9+D5*E9+D6*F9+D7*G9` | `portfolio_return(w, mu)` |
| `Optimal Portflio!J2` | `SQRT(MMULT(TRANSPOSE(D2:D7),MMULT(R6:W11,D2:D7))*252)` | `portfolio_volatility(w, cov_annual)` |
| `Optimal Portflio!J4` | `=(J1 - Dashboard!C6) / J2` | `sharpe_ratio(w, mu, cov_annual, rf)` |
| `Dashboard!C6` | Risk-free rate (SAMA) | `PortfolioInputs.risk_free_rate` |

## Slide 124 — Solver setup

| Solver element | Excel location | Python equivalent |
|---|---|---|
| Objective | Max `J4` | `minimize(-sharpe_ratio, ...)` or `solve_sharpe_qp` |
| Decision variables | `D2:D7` | the `w` array |
| Constraint: `w_i >= 0` | Solver "Make Unconstrained Variables Non-Negative" | `Bounds(lb=0.0, ub=1.0)` |
| Constraint: `sum(w) = 1` | `=ROUND(SUM(E2:E7),0) = 1` (cell A8) | `LinearConstraint(ones(n), 1, 1)` |
| Constraint: `sigma_p <= min_sigma_i` | `H9 = MIN(B11:G11)` | `NonlinearConstraint(vol_gap, lb=0, ub=inf)` |
| Constraint: `R_p >= R_f` | Dashboard!C6 | `NonlinearConstraint(ret_gap, lb=0, ub=inf)` |

## Slide 125 — Covariance matrix & portfolio SD

| Excel | Formula | Python |
|---|---|---|
| `Optimal Portflio!R6:W11` | `=COVAR(B17:B762, <col>17:<col>762)` for each pair | `cov_daily[i,j]` built server-side from daily returns |
| Annualization `×252` | inside `J2` array formula | `cov_annual = cov_daily * 252` |

**Important:** `COVAR` in Excel uses the population formula (dividing by N, not N-1).
NumPy's `np.cov(..., ddof=0)` matches this exactly. If you use pandas `.cov()`
or `np.cov(... )` without `ddof=0` you'll get the sample covariance (divide by
N-1) and values will be slightly larger.

## Slide 126 — Correlation matrix

| Excel | Formula | Python |
|---|---|---|
| `Investment Details!AI20:AN26` | `=CORREL(P11:P758, Q11:Q758)` | `np.corrcoef(returns_matrix, rowvar=False)` |
| `Investment Details!AI28:AN34` | Explicit Pearson formula (same result) | same |

Both formulas are mathematically identical; Formula 2 is the long-hand
of `CORREL`. They exist in the sheet for verification — keep both in the
backend QA test to guarantee numerical parity.

## Other key mappings (for the full build)

| Metric | Excel | Python location (future modules) |
|---|---|---|
| CAPM expected return | `Investment Details!P6:U6` (`=R_f + β·(R_m - R_f)`) | `capm.py :: expected_return()` |
| Beta | `Investment Details!F5` (regression slope) | `capm.py :: compute_beta()` |
| Daily returns | `Investment Details!P11:U758` | `returns.py :: daily_returns()` |
| Annual variance | `Optimal Portflio!B10:G10` (`=daily_var × 252`) | built into `cov_annual` |
| Annual SD | `Optimal Portflio!B11:G11` (`=daily_sd × sqrt(252)`) | `np.sqrt(np.diag(cov_annual))` |
| Stock Sharpe | `Optimal Portflio!B13:G13` | `(mu - rf) / sd` |
| VaR | `VaR (1..6)!K6` | `var.py :: historical_var()` or `parametric_var()` |
| Risk-free rate | `Dashboard!C6` (admin-editable) | admin config table in DB |

## Deployment notes

1. **Where optimization runs:** on the server, not the browser. The QP/SLSQP
   solvers need numerical libraries (scipy ≈ 30 MB). Expose a REST endpoint
   like `POST /api/optimize` that takes the tickers + CAPM returns + daily
   price matrix and returns the weights + frontier.
2. **Caching:** covariance matrices and CAPM expected returns should be
   precomputed nightly and cached — don't recompute from raw prices on every
   user click. This is where "Data loading time" on the admin dashboard plugs in.
3. **Parity testing:** for every release, run the solver on the exact Excel
   inputs and assert `max|w_python - w_excel| < 1e-4`. Add a fixture from the
   current workbook as the golden file.
4. **Short-selling:** Excel Solver defaults to allowing negatives unless you
   tick "non-negative". Slide 124 explicitly requires `w_i >= 0`, so the
   Python code enforces `Bounds(lb=0)`. If the admin later wants to allow
   shorting, flip `allow_shorting=True`.
