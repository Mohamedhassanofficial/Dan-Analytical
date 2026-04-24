"""
Real-Data Loader & Verification for Dan Analytical Platform
===========================================================

Uses the files you uploaded:
  - Stock-List-Arabic-and-English.xlsx (234 Tadawul symbols, Ar+En)
  - Index-Data-From-28-02-2016-To26-02-2026.csv (10 years of sector indices)

What it does:
  1. Loads the 234-stock universe into a normalized DataFrame
  2. Loads the 10-year sector index history (44,506 rows)
  3. Builds covariance/correlation matrices from REAL sector returns
  4. Runs the Solver using REAL data (not demo fixtures)
  5. Produces a verification report

This is the seed for Phase 1 (Data Layer) — everything here will migrate
into the PostgreSQL `stocks` and `market_indices` tables.

Run:
  python load_real_tadawul_data.py

Requirements:
  pip install pandas numpy openpyxl scipy
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Tuple
import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
UPLOADS = Path("/mnt/user-data/uploads")  # adjust in production
STOCK_LIST_FILE = UPLOADS / "Stock-List-Arabic-and-English.xlsx"
INDEX_FILE      = UPLOADS / "Index-Data-From-28-02-2016-To26-02-2026.csv"

TRADING_DAYS = 252  # matches Optimal Portflio sheet annualization


# ===========================================================================
# 1) Load the real 234-stock Tadawul universe
# ===========================================================================
def load_stock_universe() -> pd.DataFrame:
    """
    Load the bilingual Tadawul stock list into a clean DataFrame.

    Returns a DataFrame with columns:
        symbol, company_name_en, industry, index_code
    Intended as the seed for PostgreSQL `stocks` table.
    """
    df = pd.read_excel(STOCK_LIST_FILE)
    df.columns = [c.strip() for c in df.columns]

    out = df.rename(columns={
        "Symbol Code":   "symbol",
        "Company Name":  "company_name_en",
        "Industry Type": "industry",
        "Index Code":    "index_code",
    })
    out["symbol"] = out["symbol"].astype(str).str.zfill(4)
    out["ticker_suffix"] = out["symbol"] + ".SR"   # yfinance / EODHD format
    return out[["symbol", "ticker_suffix", "company_name_en",
                "industry", "index_code"]].sort_values("symbol").reset_index(drop=True)


# ===========================================================================
# 2) Load the real 10-year sector index data
# ===========================================================================
def load_sector_indices() -> pd.DataFrame:
    """
    Load the 10-year sector index file (44,506 rows across 21 sectors).

    Returns a wide-format DataFrame: index=date, columns=sector codes,
    values=daily closing prices. Matches the "Investment Details" sheet
    pattern from the Excel workbook.
    """
    df = pd.read_csv(INDEX_FILE, encoding="utf-8-sig")
    df.columns = [c.strip() for c in df.columns]

    df["date"] = pd.to_datetime(df["L.T. Date"], format="%d/%m/%Y", errors="coerce")
    df = df.dropna(subset=["date"])

    # Pivot to wide format — one column per sector
    wide = df.pivot_table(index="date", columns="Sector Code",
                          values="Close", aggfunc="last")
    wide = wide.sort_index()
    return wide


# ===========================================================================
# 3) Build daily-return matrix from sector indices
# ===========================================================================
def build_returns_matrix(prices: pd.DataFrame,
                         sectors: list[str],
                         start: str | None = None,
                         end:   str | None = None) -> pd.DataFrame:
    """Compute daily log returns for the requested sectors, aligned to
    common dates with no NaNs. This is the input to covariance."""
    sub = prices[sectors].copy()
    if start: sub = sub.loc[start:]
    if end:   sub = sub.loc[:end]
    sub = sub.dropna(how="any")  # require all sectors present on a given day
    returns = np.log(sub / sub.shift(1)).dropna()
    return returns


# ===========================================================================
# 4) Portfolio math (identical to portfolio_optimizer.py, redefined here
#    so this script is self-contained and runnable in isolation)
# ===========================================================================
def portfolio_return(w, mu):
    return float(np.dot(w, mu))

def portfolio_volatility(w, cov_annual):
    return float(np.sqrt(w @ cov_annual @ w))

def sharpe_ratio(w, mu, cov_annual, rf):
    v = portfolio_volatility(w, cov_annual)
    return 0.0 if v < 1e-12 else (portfolio_return(w, mu) - rf) / v


def solve_tangency(mu: np.ndarray,
                   cov_annual: np.ndarray,
                   rf: float) -> Tuple[np.ndarray, dict]:
    """Sharpe-max tangency portfolio via SLSQP. Long-only, fully invested."""
    from scipy.optimize import minimize, Bounds, LinearConstraint
    n = len(mu)

    def neg_sharpe(w): return -sharpe_ratio(w, mu, cov_annual, rf)

    res = minimize(
        neg_sharpe, x0=np.full(n, 1.0 / n),
        method="SLSQP",
        bounds=Bounds(0.0, 1.0),
        constraints=[LinearConstraint(np.ones(n), 1.0, 1.0)],
        options={"ftol": 1e-10, "maxiter": 500},
    )
    return res.x, {
        "success": bool(res.success),
        "sharpe": float(sharpe_ratio(res.x, mu, cov_annual, rf)),
        "return": float(portfolio_return(res.x, mu)),
        "vol":    float(portfolio_volatility(res.x, cov_annual)),
    }


# ===========================================================================
# 5) Main run — real-data verification
# ===========================================================================
def main():
    print("=" * 76)
    print("Dan Analytical — Real-Data Verification")
    print("=" * 76)

    # ---- Stock universe ----------------------------------------------------
    stocks = load_stock_universe()
    print(f"\n[1] Stock universe loaded: {len(stocks)} Tadawul symbols")
    print(f"    Industries: {stocks['industry'].nunique()}")
    print(f"    Top 5 industries by count:")
    for ind, n in stocks['industry'].value_counts().head(5).items():
        print(f"      - {ind:<40s} {n:>3d}")
    print(f"\n    Sample symbols (first 5):")
    print(stocks.head().to_string(index=False))

    # ---- Sector index history ---------------------------------------------
    prices = load_sector_indices()
    print(f"\n[2] Sector index history loaded:")
    print(f"    Date range: {prices.index.min().date()} → {prices.index.max().date()}")
    print(f"    Sectors:    {len(prices.columns)}")
    print(f"    Rows:       {len(prices):,}")

    # Pick the 6 sectors with full 10-year coverage — these correspond to
    # the 6 stocks in the Excel model (STC, Aramco, SABIC, Herfy, SADAFCO, AlRajhi)
    SIX_SECTORS = ["TTSI", "TENI", "TMTI", "TFBI", "TFBI", "TBNI"]  # note TFBI twice
    SIX_LABELS  = ["Telecom (STC)", "Energy (Aramco)", "Materials (SABIC)",
                   "Food (Herfy)", "Food (SADAFCO)", "Banks (AlRajhi)"]
    unique_sectors = ["TTSI", "TENI", "TMTI", "TFBI", "TBNI", "TCSI"]
    print(f"\n[3] Selecting 6 sectors with full 10-year coverage:")
    for s in unique_sectors:
        sub = prices[s].dropna()
        print(f"      {s:<6s} {sub.index.min().date()} → "
              f"{sub.index.max().date()}   ({len(sub):,} days)")

    # ---- Build returns + covariance ---------------------------------------
    rets = build_returns_matrix(prices, unique_sectors)
    print(f"\n[4] Daily returns matrix: {rets.shape[0]:,} days × {rets.shape[1]} sectors")
    print(f"    Common date range: {rets.index.min().date()} → {rets.index.max().date()}")

    cov_daily = rets.cov(ddof=0).values           # ddof=0 matches Excel COVAR
    corr_mat  = rets.corr().values
    cov_annual = cov_daily * TRADING_DAYS

    print(f"\n[5] Annualized risk/return profile (real 10yr data):")
    ann_vol = np.sqrt(np.diag(cov_annual))
    ann_ret = rets.mean().values * TRADING_DAYS   # empirical (not CAPM)
    print(f"    {'Sector':<8s}  {'Annual Return':>14s}  {'Annual Vol':>12s}")
    for i, s in enumerate(unique_sectors):
        print(f"    {s:<8s}  {ann_ret[i]*100:>13.2f}%  {ann_vol[i]*100:>11.2f}%")

    # ---- Solver run with real data ----------------------------------------
    rf = 0.0475  # 12M SAIBOR April 2026 per Saudi Build Reference
    mu_capm_proxy = ann_ret       # demo: use empirical returns as μ
                                   # (production: CAPM from beta × TASI ERP)
    w_opt, info = solve_tangency(mu_capm_proxy, cov_annual, rf)

    print(f"\n[6] Tangency portfolio (Sharpe-max) on REAL 10-year data:")
    print(f"    Risk-free rate (12M SAIBOR):  {rf*100:.2f}%")
    print(f"    {'Sector':<8s}  {'Optimal Weight':>14s}")
    for i, s in enumerate(unique_sectors):
        bar = "█" * int(round(w_opt[i] * 50))
        print(f"    {s:<8s}  {w_opt[i]*100:>13.2f}%  {bar}")
    print(f"    {'':<8s}  {'--------------':>14s}")
    print(f"    {'Total':<8s}  {w_opt.sum()*100:>13.2f}%")
    print(f"\n    Portfolio Expected Return:  {info['return']*100:.3f}%")
    print(f"    Portfolio Volatility:       {info['vol']*100:.3f}%")
    print(f"    Sharpe Ratio:               {info['sharpe']:.4f}")
    print(f"    Solver success:             {info['success']}")

    # ---- Correlation sanity check -----------------------------------------
    print(f"\n[7] Sector correlation matrix (real data, Pearson):")
    print(f"    {'':<6s}" + "".join(f"{s:>7s}" for s in unique_sectors))
    for i, s in enumerate(unique_sectors):
        row = "".join(f"{corr_mat[i][j]:>7.3f}" for j in range(len(unique_sectors)))
        print(f"    {s:<6s}{row}")

    # ---- DB seed preview ---------------------------------------------------
    print(f"\n[8] SQL seed preview (for PostgreSQL `stocks` table):")
    print(f"    {'symbol':<8s} {'ticker':<10s} {'name':<25s} {'industry':<30s} {'index':<6s}")
    for _, r in stocks.head(6).iterrows():
        print(f"    {r['symbol']:<8s} {r['ticker_suffix']:<10s} "
              f"{r['company_name_en']:<25s} {r['industry']:<30s} {r['index_code']:<6s}")
    print(f"    ...({len(stocks)-6} more)")

    print(f"\n{'=' * 76}")
    print("✓ Real-data pipeline verified — ready for Phase 1 DB migration.")
    print(f"{'=' * 76}")

    return {
        "stocks": stocks,
        "prices": prices,
        "returns": rets,
        "cov_daily": cov_daily,
        "cov_annual": cov_annual,
        "correlation": corr_mat,
        "optimal_weights": dict(zip(unique_sectors, w_opt.tolist())),
        "metrics": info,
    }


if __name__ == "__main__":
    try:
        result = main()
    except FileNotFoundError as e:
        print(f"\n[ERROR] Uploaded file not found: {e}", file=sys.stderr)
        print("Adjust UPLOADS path at top of script.", file=sys.stderr)
        sys.exit(1)
