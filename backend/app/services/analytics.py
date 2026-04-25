"""
Analytics helpers — compute returns matrices, covariance, and CAPM expected
returns from DB-stored prices. Called by the portfolio /optimize endpoint
when the caller passes just a list of tickers (DB-backed mode).

Sources
-------
- prices_daily: per-stock daily close (populated by yfinance refresher)
- sector_index_daily: sector indices (seeded from 10-year CSV)
- admin_config: risk_free_rate (SAMA), trading_days_per_year, lookback_days
- TASI index (sector_code='TASI') as the market proxy for beta regression

Outputs (all per the PDF + Excel model)
---------------------------------------
- daily_returns: T x n log returns
- cov_daily: n x n covariance (ddof=0, to match Excel COVAR)
- cov_daily_shrunk: n x n Ledoit-Wolf shrinkage covariance
- capm_expected_returns: n-vector of annual expected returns
- beta_per_stock: n-vector (raw OLS)
- beta_blume: n-vector (Blume adjusted: 0.33 + 0.67·β_raw)
- correlation: n x n correlation matrix (Pearson Formula 2)
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

import numpy as np
import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import PriceDaily, Sector, SectorIndexDaily, Stock
from app.services.covariance import (
    correlation_from_covariance,
    covariance_quality_report,
    ledoit_wolf_shrinkage_fast,
    validate_correlation_parity,
)

TASI_CODE = "TASI"


@dataclass
class UniverseAnalytics:
    tickers: list[str]              # in the same order as the other arrays
    trading_dates: list[date]
    daily_returns: np.ndarray       # T x n, log returns
    cov_daily: np.ndarray           # n x n (raw, ddof=0, Excel COVAR parity)
    cov_daily_shrunk: np.ndarray    # n x n Ledoit-Wolf shrinkage estimator
    shrinkage_intensity: float      # optimal δ* from Ledoit-Wolf
    correlation: np.ndarray         # n x n Pearson Formula 2
    correlation_parity: dict        # {max_diff, parity_pass} vs np.corrcoef
    mu_daily: np.ndarray            # n, empirical daily means
    annual_volatility: np.ndarray   # n, σ_daily · √trading_days
    beta: np.ndarray                # n, β vs TASI (raw OLS)
    beta_blume: np.ndarray          # n, Blume adjusted: 0.33 + 0.67·β_raw
    capm_expected_return: np.ndarray  # n, annual: R_f + β·(E[R_m] − R_f)
    capm_expected_return_blume: np.ndarray  # n, using Blume-adjusted β
    market_annual_return: float
    risk_free_rate: float
    trading_days_per_year: int
    cov_quality: dict | None = None  # eigenvalue spectrum, condition number


# ---------------------------------------------------------------------------
def _load_price_frame(
    db: Session, tickers: list[str], start: date, end: date
) -> pd.DataFrame:
    """
    Return a DataFrame indexed by date with one column per ticker containing
    adj_close (falling back to close). Only rows present for every ticker
    are kept so covariance alignment is clean.
    """
    rows = db.execute(
        select(Stock.ticker_suffix, PriceDaily.trade_date, PriceDaily.adj_close, PriceDaily.close)
        .join(PriceDaily, PriceDaily.stock_id == Stock.id)
        .where(
            Stock.ticker_suffix.in_(tickers),
            PriceDaily.trade_date >= start,
            PriceDaily.trade_date <= end,
        )
        .order_by(PriceDaily.trade_date)
    ).all()

    if not rows:
        raise ValueError(
            f"No prices in DB for tickers={tickers} between {start} and {end}. "
            "Run `python -m scripts.refresh_prices` first."
        )

    df = pd.DataFrame(rows, columns=["ticker", "trade_date", "adj_close", "close"])
    df["price"] = df["adj_close"].astype("float64").fillna(df["close"].astype("float64"))
    wide = df.pivot(index="trade_date", columns="ticker", values="price").sort_index()

    # Only keep tickers we asked for, in the requested order
    missing = [t for t in tickers if t not in wide.columns]
    if missing:
        raise ValueError(f"DB is missing price history for: {missing}")
    return wide[tickers].dropna(how="any")


def _load_market_returns(db: Session, start: date, end: date) -> pd.Series:
    """TASI daily returns series, indexed by trade_date."""
    tasi = db.execute(
        select(Sector).where(Sector.sector_code == TASI_CODE)
    ).scalar_one_or_none()
    if tasi is None:
        raise ValueError(
            "TASI sector not seeded. Run `python -m scripts.seed_stocks` first."
        )

    rows = db.execute(
        select(SectorIndexDaily.trade_date, SectorIndexDaily.close)
        .where(
            SectorIndexDaily.sector_id == tasi.id,
            SectorIndexDaily.trade_date >= start,
            SectorIndexDaily.trade_date <= end,
        )
        .order_by(SectorIndexDaily.trade_date)
    ).all()
    if not rows:
        raise ValueError("No TASI index history in sector_index_daily.")

    s = pd.Series(
        {r.trade_date: float(r.close) for r in rows},
        name=TASI_CODE,
    )
    return np.log(s / s.shift(1)).dropna()


# ---------------------------------------------------------------------------
# Blume beta adjustment — mean-reversion correction
# ---------------------------------------------------------------------------
def blume_adjust_beta(raw_beta: np.ndarray) -> np.ndarray:
    """
    Blume (1975) adjustment: β_adj = 0.33 + 0.67 · β_raw.

    Corrects for the well-documented tendency of betas to regress toward 1.0
    over time. Bloomberg and most commercial platforms use this adjustment.
    """
    return 0.33 + 0.67 * np.asarray(raw_beta, dtype=np.float64)


# ---------------------------------------------------------------------------
def compute_universe_analytics(
    db: Session,
    tickers: list[str],
    lookback_days: int,
    risk_free_rate: float,
    trading_days_per_year: int,
    end: date | None = None,
    use_shrinkage: bool = False,
) -> UniverseAnalytics:
    """
    Fetch prices, compute returns + covariance + CAPM for `tickers`.

    `lookback_days` is the trading-day window; we widen by 40% on calendar
    days to account for weekends/holidays, then trim to the last N rows.

    New in Phase 2:
      - Ledoit-Wolf shrinkage covariance (always computed, optionally used)
      - Blume-adjusted betas
      - Pearson Formula 2 correlation cross-check
      - Covariance quality report
    """
    end = end or date.today()
    calendar_days = int(lookback_days * 7 / 5) + 30  # weekends + buffer
    start = end - timedelta(days=calendar_days)

    prices = _load_price_frame(db, tickers, start, end)
    if len(prices) < 30:
        raise ValueError(
            f"Only {len(prices)} common trading days found for the requested "
            f"tickers — need at least 30 for meaningful statistics."
        )
    prices = prices.tail(lookback_days)

    returns = np.log(prices / prices.shift(1)).dropna()
    returns_arr = returns.to_numpy()

    # ---- Covariance (raw + shrunk) -----------------------------------------
    cov_daily = np.cov(returns_arr, rowvar=False, ddof=0)  # matches Excel COVAR
    cov_shrunk, shrinkage = ledoit_wolf_shrinkage_fast(returns_arr)

    # ---- Correlation (Pearson Formula 2 + cross-check) --------------------
    corr_matrix = correlation_from_covariance(cov_daily)
    corr_parity = validate_correlation_parity(returns_arr, cov_daily)

    # ---- Covariance quality ------------------------------------------------
    quality = covariance_quality_report(cov_daily)
    cov_quality = {
        "condition_number": quality.condition_number,
        "is_psd": quality.is_psd,
        "min_eigenvalue": quality.min_eigenvalue,
        "suggested_shrinkage": quality.suggested_shrinkage,
    }

    mu_daily = returns_arr.mean(axis=0)
    annual_vol = np.sqrt(np.diag(cov_daily) * trading_days_per_year)

    market = _load_market_returns(db, start, end).reindex(returns.index).dropna()
    common_idx = returns.index.intersection(market.index)
    returns_aligned = returns.loc[common_idx].to_numpy()
    market_aligned = market.loc[common_idx].to_numpy()

    # ---- Beta (raw OLS + Blume) -------------------------------------------
    # β_i = Cov(R_i, R_m) / Var(R_m)
    market_var = float(np.var(market_aligned, ddof=0))
    if market_var <= 1e-16:
        raise ValueError("TASI variance is zero in the lookback window.")
    betas = np.array(
        [
            float(np.cov(returns_aligned[:, i], market_aligned, ddof=0)[0, 1]) / market_var
            for i in range(returns_aligned.shape[1])
        ]
    )
    betas_blume = blume_adjust_beta(betas)

    # ---- CAPM expected returns (raw + Blume) -------------------------------
    market_annual_return = float(market_aligned.mean() * trading_days_per_year)
    equity_risk_premium = market_annual_return - risk_free_rate
    capm_annual = risk_free_rate + betas * equity_risk_premium
    capm_annual_blume = risk_free_rate + betas_blume * equity_risk_premium

    return UniverseAnalytics(
        tickers=list(tickers),
        trading_dates=list(returns.index),
        daily_returns=returns_arr,
        cov_daily=cov_daily,
        cov_daily_shrunk=cov_shrunk,
        shrinkage_intensity=shrinkage,
        correlation=corr_matrix,
        correlation_parity=corr_parity,
        mu_daily=mu_daily,
        annual_volatility=annual_vol,
        beta=betas,
        beta_blume=betas_blume,
        capm_expected_return=capm_annual,
        capm_expected_return_blume=capm_annual_blume,
        market_annual_return=market_annual_return,
        risk_free_rate=risk_free_rate,
        trading_days_per_year=trading_days_per_year,
        cov_quality=cov_quality,
    )


def min_individual_annual_sd(annual_volatility: np.ndarray) -> float:
    """Excel: Optimal Portflio!H9 = MIN(B11:G11) — the σ_p cap constraint."""
    return float(np.min(annual_volatility))
