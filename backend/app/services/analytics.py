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
- capm_expected_returns: n-vector of annual expected returns
- beta_per_stock: n-vector
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

import numpy as np
import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import PriceDaily, Sector, SectorIndexDaily, Stock

TASI_CODE = "TASI"


@dataclass
class UniverseAnalytics:
    tickers: list[str]              # in the same order as the other arrays
    trading_dates: list[date]
    daily_returns: np.ndarray       # T x n, log returns
    cov_daily: np.ndarray           # n x n
    mu_daily: np.ndarray            # n, empirical daily means
    annual_volatility: np.ndarray   # n, σ_daily · √trading_days
    beta: np.ndarray                # n, β vs TASI
    capm_expected_return: np.ndarray  # n, annual: R_f + β·(E[R_m] − R_f)
    market_annual_return: float
    risk_free_rate: float
    trading_days_per_year: int


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
def compute_universe_analytics(
    db: Session,
    tickers: list[str],
    lookback_days: int,
    risk_free_rate: float,
    trading_days_per_year: int,
    end: date | None = None,
) -> UniverseAnalytics:
    """
    Fetch prices, compute returns + covariance + CAPM for `tickers`.

    `lookback_days` is the trading-day window; we widen by 40% on calendar
    days to account for weekends/holidays, then trim to the last N rows.
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

    cov_daily = np.cov(returns_arr, rowvar=False, ddof=0)  # matches Excel COVAR
    mu_daily = returns_arr.mean(axis=0)
    annual_vol = np.sqrt(np.diag(cov_daily) * trading_days_per_year)

    market = _load_market_returns(db, start, end).reindex(returns.index).dropna()
    common_idx = returns.index.intersection(market.index)
    returns_aligned = returns.loc[common_idx].to_numpy()
    market_aligned = market.loc[common_idx].to_numpy()

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

    market_annual_return = float(market_aligned.mean() * trading_days_per_year)
    equity_risk_premium = market_annual_return - risk_free_rate
    capm_annual = risk_free_rate + betas * equity_risk_premium

    return UniverseAnalytics(
        tickers=list(tickers),
        trading_dates=list(returns.index),
        daily_returns=returns_arr,
        cov_daily=cov_daily,
        mu_daily=mu_daily,
        annual_volatility=annual_vol,
        beta=betas,
        capm_expected_return=capm_annual,
        market_annual_return=market_annual_return,
        risk_free_rate=risk_free_rate,
        trading_days_per_year=trading_days_per_year,
    )


def min_individual_annual_sd(annual_volatility: np.ndarray) -> float:
    """Excel: Optimal Portflio!H9 = MIN(B11:G11) — the σ_p cap constraint."""
    return float(np.min(annual_volatility))
