"""
Populate ALL active stocks (not just the curated 25) with sector-coherent
synthetic analytics so the Screener has real numbers across all 234 rows
for the demo.

Approach:
  1. Define a profile per sector: mean β, σ ranges, P/E ranges, etc., loosely
     informed by Saudi-market sector norms (Banks lower β + lower σ, Materials
     higher β, Real Estate higher σ, etc.)
  2. For each stock, sample within its sector's profile using a deterministic
     seed (so re-runs produce identical numbers).
  3. Risk Ranking is derived from the sampled annual_volatility — so the
     spread across the universe matches the spec's expected distribution.
  4. Idempotent: re-running overwrites all values with the same numbers.

This is DEMO data. Production replaces it via the admin Excel upload
(`/api/v1/admin/upload/stock-fundamentals`).
"""
from __future__ import annotations

import sys
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

import numpy as np
from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.models import Stock  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.services.stock_analytics import compute_risk_ranking  # noqa: E402


# ── Sector profiles ────────────────────────────────────────────────────────
# Each profile is the sampling parameters for that sector. Wide ranges for
# emerging-market / cyclical sectors; tight ranges for utilities / banks.
#
# Keys: sector_code → dict with parameter ranges.
PROFILE_DEFAULT = {
    "beta": (0.8, 1.20),
    "ann_vol": (0.20, 0.32),
    "capm_mu": (0.06, 0.11),
    "pe": (15.0, 28.0),
    "eps": (0.5, 4.0),
    "div_yield": (0.005, 0.045),
    "div_rate": (0.2, 2.5),
    "roe": (0.05, 0.18),
    "mb": (1.5, 3.5),
    "fcf_yield": (0.01, 0.06),
    "leverage": (0.20, 0.80),
    "last_price": (15.0, 80.0),
}

PROFILES: dict[str, dict[str, tuple[float, float]]] = {
    # Conservative / lower-vol sectors
    "TBNI": {  # Banks (Al Rajhi, NCB, Riyad, Saudi British, etc.)
        "beta": (0.65, 0.95),  "ann_vol": (0.10, 0.16),
        "capm_mu": (0.07, 0.11), "pe": (9.0, 15.0), "eps": (2.5, 7.0),
        "div_yield": (0.030, 0.055), "div_rate": (1.5, 4.0),
        "roe": (0.12, 0.18),  "mb": (1.5, 2.8), "fcf_yield": (0.04, 0.08),
        # Saudi banks run D/E 5-9x. Numeric leverage ratio reflects that.
        "leverage": (5.0, 9.5), "last_price": (20.0, 90.0),
    },
    "TTSI": {  # Telecom (STC, Mobily, Zain, etc.)
        "beta": (0.55, 0.85), "ann_vol": (0.10, 0.16),
        "capm_mu": (0.06, 0.10), "pe": (12.0, 22.0), "eps": (2.0, 4.5),
        "div_yield": (0.045, 0.070), "div_rate": (1.5, 3.0),
        "roe": (0.10, 0.18), "mb": (1.8, 3.5), "fcf_yield": (0.05, 0.085),
        "leverage": (0.80, 1.80), "last_price": (28.0, 50.0),
    },
    "TUTI": {  # Utilities (Saudi Electric, NWC, etc. — capital-heavy + regulated)
        "beta": (0.50, 0.80), "ann_vol": (0.11, 0.18),
        "capm_mu": (0.05, 0.09), "pe": (14.0, 28.0), "eps": (0.5, 2.5),
        "div_yield": (0.025, 0.050), "div_rate": (0.5, 2.0),
        "roe": (0.06, 0.12), "mb": (1.0, 2.0), "fcf_yield": (0.020, 0.055),
        "leverage": (1.20, 2.40), "last_price": (16.0, 32.0),
    },
    # Moderate-vol sectors
    "TENI": {  # Energy (Aramco, Petro Rabigh, Bahri, Aldrees, ADES, etc.)
        "beta": (0.75, 1.10), "ann_vol": (0.14, 0.24),
        "capm_mu": (0.07, 0.12), "pe": (10.0, 22.0), "eps": (1.0, 3.0),
        "div_yield": (0.050, 0.085), "div_rate": (1.0, 2.5),
        "roe": (0.08, 0.20), "mb": (1.5, 4.5), "fcf_yield": (0.05, 0.10),
        "leverage": (0.20, 0.80), "last_price": (22.0, 55.0),
    },
    "TFBI": {  # Food & Beverages (Almarai, Sadafco, Savola, etc.)
        "beta": (0.65, 0.95), "ann_vol": (0.13, 0.22),
        "capm_mu": (0.06, 0.10), "pe": (14.0, 30.0), "eps": (1.0, 4.0),
        "div_yield": (0.018, 0.045), "div_rate": (0.5, 2.5),
        "roe": (0.08, 0.18), "mb": (1.5, 4.0), "fcf_yield": (0.025, 0.060),
        "leverage": (0.40, 1.00), "last_price": (35.0, 180.0),
    },
    "TRTI": {  # Transportation (Saudi Airlines Catering, Aldrees, etc.)
        "beta": (0.85, 1.20), "ann_vol": (0.18, 0.30),
        "capm_mu": (0.07, 0.11), "pe": (14.0, 28.0), "eps": (0.8, 3.5),
        "div_yield": (0.015, 0.045), "div_rate": (0.4, 1.8),
        "roe": (0.08, 0.18), "mb": (1.5, 3.2), "fcf_yield": (0.025, 0.060),
        "leverage": (0.50, 1.50), "last_price": (18.0, 60.0),
    },
    # Higher-vol sectors
    "TMTI": {  # Materials (Sabic, Ma'aden, Yamamah, etc. — largest sector)
        "beta": (0.95, 1.30), "ann_vol": (0.18, 0.30),
        "capm_mu": (0.07, 0.12), "pe": (10.0, 28.0), "eps": (0.8, 5.0),
        "div_yield": (0.020, 0.050), "div_rate": (0.5, 3.0),
        "roe": (0.05, 0.18), "mb": (1.2, 3.0), "fcf_yield": (0.020, 0.060),
        "leverage": (0.40, 1.20), "last_price": (15.0, 110.0),
    },
    "TCSI": {  # Capital Goods (Saudi Cable, Yamama Cement, contractors, etc.)
        "beta": (0.95, 1.30), "ann_vol": (0.20, 0.32),
        "capm_mu": (0.08, 0.12), "pe": (14.0, 30.0), "eps": (0.8, 3.0),
        "div_yield": (0.010, 0.035), "div_rate": (0.3, 1.5),
        "roe": (0.06, 0.15), "mb": (1.2, 2.8), "fcf_yield": (0.015, 0.050),
        "leverage": (0.50, 1.40), "last_price": (15.0, 50.0),
    },
    "TDFI": {  # Diversified Financials (Tadawul Group, AlAhli Capital, etc.)
        "beta": (0.85, 1.15), "ann_vol": (0.16, 0.26),
        "capm_mu": (0.07, 0.11), "pe": (12.0, 24.0), "eps": (0.8, 3.0),
        "div_yield": (0.020, 0.045), "div_rate": (0.3, 1.5),
        "roe": (0.08, 0.18), "mb": (1.2, 2.8), "fcf_yield": (0.020, 0.055),
        "leverage": (1.00, 2.50), "last_price": (15.0, 50.0),
    },
    "TISI": {  # Insurance (Tawuniya, Bupa, Walaa, etc. — volatile, some loss years)
        "beta": (0.85, 1.20), "ann_vol": (0.20, 0.32),
        "capm_mu": (0.06, 0.11), "pe": (14.0, 28.0), "eps": (0.3, 2.5),
        "div_yield": (0.010, 0.035), "div_rate": (0.2, 1.2),
        "roe": (0.04, 0.15), "mb": (1.0, 2.5), "fcf_yield": (0.015, 0.050),
        "leverage": (0.30, 0.90), "last_price": (18.0, 80.0),
    },
    # Aggressive / very aggressive sectors
    "TRMI": {  # Real Estate Management & Development
        "beta": (1.05, 1.45), "ann_vol": (0.26, 0.40),
        "capm_mu": (0.08, 0.13), "pe": (12.0, 30.0), "eps": (0.4, 2.5),
        "div_yield": (0.010, 0.045), "div_rate": (0.2, 1.5),
        "roe": (0.04, 0.18), "mb": (0.9, 2.2), "fcf_yield": (0.015, 0.070),
        "leverage": (0.60, 2.00), "last_price": (12.0, 40.0),
    },
    "TRLI": {  # REITs (legally distribute most income — high yield)
        "beta": (0.80, 1.05), "ann_vol": (0.14, 0.22),
        "capm_mu": (0.06, 0.10), "pe": (12.0, 22.0), "eps": (0.4, 1.5),
        "div_yield": (0.060, 0.100), "div_rate": (0.5, 1.5),
        "roe": (0.06, 0.12), "mb": (0.8, 1.4), "fcf_yield": (0.04, 0.085),
        "leverage": (0.40, 1.10), "last_price": (8.0, 14.0),
    },
    "TPBI": {  # Pharma/Biotech (re-invest most earnings)
        "beta": (1.00, 1.30), "ann_vol": (0.24, 0.36),
        "capm_mu": (0.08, 0.12), "pe": (22.0, 50.0), "eps": (0.5, 3.0),
        "div_yield": (0.000, 0.020), "div_rate": (0.0, 0.8),
        "roe": (0.08, 0.20), "mb": (3.0, 7.0), "fcf_yield": (0.015, 0.045),
        "leverage": (0.20, 0.70), "last_price": (40.0, 130.0),
    },
    # Additional sectors present in the DB (previously fell back to default)
    "TCGI": {  # Consumer Durables & Apparel (Fawaz Alhokair, Jarir, etc.)
        "beta": (0.85, 1.20), "ann_vol": (0.18, 0.30),
        "capm_mu": (0.07, 0.11), "pe": (12.0, 26.0), "eps": (1.0, 4.0),
        "div_yield": (0.020, 0.050), "div_rate": (0.5, 2.5),
        "roe": (0.10, 0.20), "mb": (2.0, 5.0), "fcf_yield": (0.030, 0.070),
        "leverage": (0.30, 1.00), "last_price": (25.0, 180.0),
    },
    "TCPI": {  # Consumer Services (Herfy, AlOthaim, hospitality, etc.)
        "beta": (0.85, 1.15), "ann_vol": (0.18, 0.28),
        "capm_mu": (0.07, 0.11), "pe": (15.0, 30.0), "eps": (0.8, 3.5),
        "div_yield": (0.015, 0.040), "div_rate": (0.4, 2.0),
        "roe": (0.10, 0.20), "mb": (2.0, 4.5), "fcf_yield": (0.025, 0.060),
        "leverage": (0.30, 1.10), "last_price": (35.0, 90.0),
    },
    "TDAI": {  # Health Care Equipment & Services (Mouwasat, Care, Hammadi)
        "beta": (0.75, 1.05), "ann_vol": (0.16, 0.26),
        "capm_mu": (0.07, 0.11), "pe": (18.0, 35.0), "eps": (1.0, 3.5),
        "div_yield": (0.010, 0.030), "div_rate": (0.3, 1.5),
        "roe": (0.10, 0.20), "mb": (2.5, 5.0), "fcf_yield": (0.025, 0.055),
        "leverage": (0.30, 1.00), "last_price": (50.0, 200.0),
    },
    "THEI": {  # Health Care (alternative GICS code; same range as TDAI)
        "beta": (0.75, 1.05), "ann_vol": (0.16, 0.26),
        "capm_mu": (0.07, 0.11), "pe": (18.0, 35.0), "eps": (1.0, 3.5),
        "div_yield": (0.010, 0.030), "div_rate": (0.3, 1.5),
        "roe": (0.10, 0.20), "mb": (2.5, 5.0), "fcf_yield": (0.025, 0.055),
        "leverage": (0.30, 1.00), "last_price": (50.0, 200.0),
    },
    "TFSI": {  # Food & Staples Retailing (Bin Dawood, Panda, Othaim Markets)
        "beta": (0.65, 0.95), "ann_vol": (0.14, 0.22),
        "capm_mu": (0.06, 0.10), "pe": (16.0, 28.0), "eps": (0.8, 3.0),
        "div_yield": (0.015, 0.040), "div_rate": (0.5, 2.0),
        "roe": (0.08, 0.16), "mb": (1.8, 3.5), "fcf_yield": (0.020, 0.055),
        "leverage": (0.40, 1.20), "last_price": (40.0, 120.0),
    },
    "TMDI": {  # Media & Entertainment (MBC, Tihama, etc.)
        "beta": (0.95, 1.25), "ann_vol": (0.20, 0.32),
        "capm_mu": (0.08, 0.12), "pe": (15.0, 35.0), "eps": (0.5, 3.0),
        "div_yield": (0.005, 0.030), "div_rate": (0.1, 1.5),
        "roe": (0.06, 0.15), "mb": (1.8, 4.5), "fcf_yield": (0.015, 0.050),
        "leverage": (0.30, 1.20), "last_price": (20.0, 100.0),
    },
    "TSSI": {  # Software & Services (Elm, Solutions, etc. — growth tech)
        "beta": (0.95, 1.30), "ann_vol": (0.20, 0.34),
        "capm_mu": (0.08, 0.13), "pe": (25.0, 60.0), "eps": (1.0, 6.0),
        "div_yield": (0.005, 0.025), "div_rate": (0.1, 1.5),
        "roe": (0.12, 0.25), "mb": (4.0, 10.0), "fcf_yield": (0.020, 0.055),
        "leverage": (0.20, 0.80), "last_price": (50.0, 350.0),
    },
    "TTNI": {  # Tech Hardware
        "beta": (0.95, 1.30), "ann_vol": (0.20, 0.32),
        "capm_mu": (0.08, 0.12), "pe": (15.0, 35.0), "eps": (0.5, 3.0),
        "div_yield": (0.010, 0.035), "div_rate": (0.2, 1.5),
        "roe": (0.08, 0.18), "mb": (2.0, 5.0), "fcf_yield": (0.020, 0.055),
        "leverage": (0.30, 1.00), "last_price": (20.0, 100.0),
    },
    "THPI": {  # Household & Personal Products (ALMAJED OUD — luxury / niche)
        "beta": (0.80, 1.10), "ann_vol": (0.18, 0.28),
        "capm_mu": (0.06, 0.10), "pe": (18.0, 32.0), "eps": (0.6, 2.5),
        "div_yield": (0.010, 0.035), "div_rate": (0.2, 1.5),
        "roe": (0.08, 0.18), "mb": (2.0, 4.5), "fcf_yield": (0.020, 0.050),
        "leverage": (0.25, 0.85), "last_price": (30.0, 90.0),
    },
}


def _sample(rng: np.random.Generator, profile: dict, key: str) -> float:
    lo, hi = profile.get(key, PROFILE_DEFAULT[key])
    return float(rng.uniform(lo, hi))


# ── Extended ratios (Loay slide 79) ─────────────────────────────────────────
# Generic baseline that fits a typical Saudi industrial firm. Per-sector
# overrides below capture the cases where reality diverges materially —
# banks have no inventory, retailers turn inventory 8-12×/yr, REITs have
# almost zero turnover, etc.
EXTRAS_DEFAULT = {
    # Liquidity
    "current_ratio":           (1.10, 2.20),
    "quick_ratio":             (0.70, 1.60),
    "cash_ratio":              (0.20, 0.80),
    "interest_coverage_ratio": (3.0, 12.0),
    # Efficiency
    "asset_turnover":          (0.40, 1.20),
    "inventory_turnover":      (3.0, 8.0),
    "receivables_turnover":    (4.0, 10.0),
    "payables_turnover":       (4.0, 9.0),
    # Profitability
    "roa":                     (0.04, 0.12),
    "net_profit_margin":       (0.06, 0.18),
    "gross_profit_margin":     (0.20, 0.45),
    # Per-Share
    "book_value_per_share":    (8.0, 35.0),
    "revenue_per_share":       (5.0, 50.0),
    # Shariah
    "debt_to_market_cap":      (0.05, 0.30),
    "cash_to_assets":          (0.05, 0.20),
    "receivables_to_assets":   (0.10, 0.30),
}

EXTRAS_BY_SECTOR: dict[str, dict[str, tuple[float, float]]] = {
    "TBNI": {  # Banks have no inventory; "current_ratio" doesn't apply the
        "current_ratio":         (0.90, 1.20),
        "quick_ratio":           (0.85, 1.15),
        "cash_ratio":            (0.10, 0.30),
        "asset_turnover":        (0.04, 0.08),
        "inventory_turnover":    (0.0, 0.0),
        "receivables_turnover":  (0.30, 0.80),
        "payables_turnover":     (0.50, 1.20),
        "interest_coverage_ratio": (1.5, 4.5),
        "roa":                   (0.012, 0.022),
        "net_profit_margin":     (0.30, 0.50),
        "gross_profit_margin":   (0.55, 0.80),
        "book_value_per_share":  (15.0, 30.0),
        "revenue_per_share":     (3.0, 12.0),
        "debt_to_market_cap":    (0.50, 1.20),
        "cash_to_assets":        (0.05, 0.18),
        "receivables_to_assets": (0.55, 0.80),
    },
    "TTSI": {  # Telecom — heavy assets, recurring billing
        "asset_turnover":        (0.40, 0.65),
        "inventory_turnover":    (8.0, 18.0),
        "net_profit_margin":     (0.10, 0.20),
        "gross_profit_margin":   (0.45, 0.65),
        "interest_coverage_ratio": (5.0, 12.0),
        "current_ratio":         (0.80, 1.40),
    },
    "TUTI": {  # Utilities — capital-heavy, regulated
        "asset_turnover":        (0.20, 0.45),
        "inventory_turnover":    (5.0, 12.0),
        "net_profit_margin":     (0.05, 0.12),
        "gross_profit_margin":   (0.20, 0.35),
        "interest_coverage_ratio": (2.0, 5.0),
        "current_ratio":         (0.70, 1.30),
    },
    "TENI": {  # Energy
        "asset_turnover":        (0.50, 1.20),
        "inventory_turnover":    (6.0, 14.0),
        "net_profit_margin":     (0.10, 0.30),
        "gross_profit_margin":   (0.25, 0.55),
        "interest_coverage_ratio": (8.0, 25.0),
        "current_ratio":         (1.20, 2.50),
    },
    "TFBI": {  # Food & Beverages
        "asset_turnover":        (0.80, 1.50),
        "inventory_turnover":    (5.0, 10.0),
        "net_profit_margin":     (0.06, 0.15),
        "gross_profit_margin":   (0.25, 0.45),
    },
    "TFSI": {  # Food & Staples Retailing — high inventory turnover, thin margins
        "asset_turnover":        (1.50, 3.00),
        "inventory_turnover":    (8.0, 14.0),
        "net_profit_margin":     (0.02, 0.06),
        "gross_profit_margin":   (0.18, 0.28),
    },
    "TCGI": {  # Consumer Durables / Apparel — high inventory turnover
        "asset_turnover":        (1.00, 2.20),
        "inventory_turnover":    (4.0, 9.0),
        "net_profit_margin":     (0.06, 0.14),
        "gross_profit_margin":   (0.30, 0.45),
    },
    "TCPI": {  # Consumer Services
        "asset_turnover":        (1.10, 2.30),
        "inventory_turnover":    (10.0, 25.0),
        "net_profit_margin":     (0.06, 0.14),
        "gross_profit_margin":   (0.30, 0.50),
    },
    "TMTI": {  # Materials — moderate turnover, cyclical margins
        "asset_turnover":        (0.50, 1.20),
        "inventory_turnover":    (4.0, 9.0),
        "net_profit_margin":     (0.06, 0.18),
        "gross_profit_margin":   (0.22, 0.40),
    },
    "TCSI": {  # Capital Goods
        "asset_turnover":        (0.60, 1.20),
        "inventory_turnover":    (3.0, 7.0),
        "net_profit_margin":     (0.04, 0.12),
        "gross_profit_margin":   (0.18, 0.32),
    },
    "TRTI": {  # Transportation
        "asset_turnover":        (0.45, 1.00),
        "inventory_turnover":    (10.0, 25.0),
        "net_profit_margin":     (0.05, 0.14),
        "gross_profit_margin":   (0.22, 0.38),
    },
    "TISI": {  # Insurance
        "asset_turnover":        (0.20, 0.45),
        "inventory_turnover":    (0.0, 0.0),
        "current_ratio":         (1.05, 1.80),
        "net_profit_margin":     (0.04, 0.12),
        "gross_profit_margin":   (0.10, 0.25),
        "debt_to_market_cap":    (0.10, 0.40),
        "receivables_to_assets": (0.30, 0.55),
    },
    "TDFI": {  # Diversified Financials
        "asset_turnover":        (0.10, 0.30),
        "inventory_turnover":    (0.0, 0.0),
        "net_profit_margin":     (0.20, 0.45),
        "gross_profit_margin":   (0.50, 0.80),
        "debt_to_market_cap":    (0.30, 1.10),
    },
    "TRMI": {  # Real Estate Management & Development
        "asset_turnover":        (0.15, 0.45),
        "inventory_turnover":    (0.5, 2.5),
        "net_profit_margin":     (0.10, 0.30),
        "gross_profit_margin":   (0.30, 0.55),
        "current_ratio":         (1.20, 3.50),
    },
    "TRLI": {  # REITs — distribute income; very low inventory turnover
        "asset_turnover":        (0.08, 0.18),
        "inventory_turnover":    (0.0, 0.0),
        "net_profit_margin":     (0.30, 0.65),
        "gross_profit_margin":   (0.55, 0.85),
        "current_ratio":         (0.90, 1.50),
    },
    "TPBI": {  # Pharma — high gross margins, modest inventory turnover
        "asset_turnover":        (0.45, 0.85),
        "inventory_turnover":    (3.0, 6.0),
        "net_profit_margin":     (0.12, 0.28),
        "gross_profit_margin":   (0.45, 0.70),
    },
    "TDAI": {  # Healthcare equipment / providers
        "asset_turnover":        (0.50, 1.10),
        "inventory_turnover":    (4.0, 9.0),
        "net_profit_margin":     (0.10, 0.22),
        "gross_profit_margin":   (0.30, 0.55),
    },
    "THEI": {  # Healthcare alt code
        "asset_turnover":        (0.50, 1.10),
        "inventory_turnover":    (4.0, 9.0),
        "net_profit_margin":     (0.10, 0.22),
        "gross_profit_margin":   (0.30, 0.55),
    },
    "TSSI": {  # Software & Services — high gross margin, no inventory
        "asset_turnover":        (0.50, 1.10),
        "inventory_turnover":    (0.0, 0.0),
        "net_profit_margin":     (0.15, 0.32),
        "gross_profit_margin":   (0.55, 0.82),
        "current_ratio":         (1.50, 3.50),
    },
    "TMDI": {  # Media
        "asset_turnover":        (0.50, 1.10),
        "inventory_turnover":    (5.0, 12.0),
        "net_profit_margin":     (0.06, 0.18),
        "gross_profit_margin":   (0.30, 0.55),
    },
    "TTNI": {  # Tech Hardware
        "asset_turnover":        (0.80, 1.50),
        "inventory_turnover":    (4.0, 9.0),
        "net_profit_margin":     (0.06, 0.16),
        "gross_profit_margin":   (0.20, 0.40),
    },
}


def _sample_extra(rng: np.random.Generator, sector_code: str | None, key: str) -> float:
    """Sample an extended ratio; sector overrides win over EXTRAS_DEFAULT."""
    sector = EXTRAS_BY_SECTOR.get(sector_code or "", {})
    lo, hi = sector.get(key, EXTRAS_DEFAULT[key])
    if lo == hi:
        return float(lo)
    return float(rng.uniform(lo, hi))


def seed() -> int:
    today = date.today()
    now = datetime.now(timezone.utc)
    updated = 0

    with SessionLocal() as db:
        stocks = db.execute(
            select(Stock).where(Stock.is_active.is_(True))
        ).scalars().all()

        for s in stocks:
            sector_code = s.sector.sector_code if s.sector else None
            profile = PROFILES.get(sector_code or "", PROFILE_DEFAULT)

            # Deterministic per-stock seed → re-runs produce identical numbers
            rng = np.random.default_rng(int(s.symbol) if s.symbol.isdigit() else hash(s.symbol) % 10**8)

            beta = _sample(rng, profile, "beta")
            ann_vol = _sample(rng, profile, "ann_vol")
            daily_vol = ann_vol / float(np.sqrt(252))
            capm_mu = _sample(rng, profile, "capm_mu")
            sharpe = (capm_mu - 0.0475) / max(ann_vol, 0.001)
            # Parametric VaR 95% 1-day (μ - z·σ); z=1.6449
            var_1d = max(0.0, -(capm_mu / 252 - 1.6449 * daily_vol))
            pe = _sample(rng, profile, "pe")
            eps = _sample(rng, profile, "eps")
            div_yield = _sample(rng, profile, "div_yield")
            div_rate = _sample(rng, profile, "div_rate")
            roe = _sample(rng, profile, "roe")
            mb = _sample(rng, profile, "mb")
            fcf_yield = _sample(rng, profile, "fcf_yield")
            leverage = _sample(rng, profile, "leverage")
            last_price = _sample(rng, profile, "last_price")

            # Inject a few negatives (~10% of stocks) for visual variety on the
            # "negative number = red" coloring rule. Cyclical sectors more likely.
            if sector_code in ("TMTI", "TRMI", "TCSI", "TPBI") and rng.random() < 0.18:
                pe = -abs(pe) * rng.uniform(0.2, 0.8)  # loss-making P/E
                eps = -abs(eps) * rng.uniform(0.3, 0.9)
            if rng.random() < 0.05:
                sharpe = -abs(sharpe) * rng.uniform(0.1, 0.5)

            s.beta = Decimal(str(round(beta, 6)))
            s.annual_volatility = Decimal(str(round(ann_vol, 6)))
            s.daily_volatility = Decimal(str(round(daily_vol, 6)))
            s.capm_expected_return = Decimal(str(round(capm_mu, 6)))
            s.sharp_ratio = Decimal(str(round(sharpe, 6)))
            s.var_95_daily = Decimal(str(round(var_1d, 6)))
            s.pe_ratio = Decimal(str(round(pe, 4)))
            s.eps = Decimal(str(round(eps, 4)))
            s.dividend_yield = Decimal(str(round(div_yield, 6)))
            s.annual_dividend_rate = Decimal(str(round(div_rate, 4)))
            s.roe = Decimal(str(round(roe, 6)))
            s.market_to_book = Decimal(str(round(mb, 4)))
            s.fcf_yield = Decimal(str(round(fcf_yield, 6)))
            s.leverage_ratio = Decimal(str(round(leverage, 6)))
            s.last_price = Decimal(str(round(last_price, 4)))
            s.last_price_date = today
            s.risk_ranking = compute_risk_ranking(s.annual_volatility)
            s.last_analytics_refresh = now

            # Extended ratios (Loay slide 79). Sampled from EXTRAS_BY_SECTOR
            # with EXTRAS_DEFAULT fallback. Per-share values use last_price as
            # an anchor so BVPS / RPS scale with the stock instead of being
            # nonsensical absolute numbers.
            s.current_ratio = Decimal(str(round(_sample_extra(rng, sector_code, "current_ratio"), 4)))
            s.quick_ratio = Decimal(str(round(_sample_extra(rng, sector_code, "quick_ratio"), 4)))
            s.cash_ratio = Decimal(str(round(_sample_extra(rng, sector_code, "cash_ratio"), 4)))
            s.interest_coverage_ratio = Decimal(str(round(_sample_extra(rng, sector_code, "interest_coverage_ratio"), 4)))
            s.asset_turnover = Decimal(str(round(_sample_extra(rng, sector_code, "asset_turnover"), 4)))
            s.inventory_turnover = Decimal(str(round(_sample_extra(rng, sector_code, "inventory_turnover"), 4)))
            s.receivables_turnover = Decimal(str(round(_sample_extra(rng, sector_code, "receivables_turnover"), 4)))
            s.payables_turnover = Decimal(str(round(_sample_extra(rng, sector_code, "payables_turnover"), 4)))
            s.roa = Decimal(str(round(_sample_extra(rng, sector_code, "roa"), 6)))
            s.net_profit_margin = Decimal(str(round(_sample_extra(rng, sector_code, "net_profit_margin"), 6)))
            s.gross_profit_margin = Decimal(str(round(_sample_extra(rng, sector_code, "gross_profit_margin"), 6)))
            # Per-share values anchored to last_price for visual coherence:
            # BVPS = price ÷ M/B (so a 100 SAR stock at M/B=2 has BVPS=50)
            # RPS  = price × revenue/asset proxy (~ 0.6 of price for industrials)
            mb_safe = float(s.market_to_book) if s.market_to_book and float(s.market_to_book) > 0 else 1.5
            bvps = max(0.5, last_price / mb_safe)
            rps = last_price * float(rng.uniform(0.30, 1.20))
            s.book_value_per_share = Decimal(str(round(bvps, 4)))
            s.revenue_per_share = Decimal(str(round(rps, 4)))
            s.debt_to_market_cap = Decimal(str(round(_sample_extra(rng, sector_code, "debt_to_market_cap"), 6)))
            s.cash_to_assets = Decimal(str(round(_sample_extra(rng, sector_code, "cash_to_assets"), 6)))
            s.receivables_to_assets = Decimal(str(round(_sample_extra(rng, sector_code, "receivables_to_assets"), 6)))

            # Disclosure dates — most issuers report quarterly. Pick a recent
            # quarter-end for balance sheet / income statement; a smaller set
            # disclose nothing (kept null). Dividend dates spread wider since
            # not every issuer pays.
            quarter_ends = (
                date(2025, 9, 30), date(2025, 6, 30), date(2025, 3, 31),
                date(2024, 12, 31), date(2024, 9, 30), date(2024, 6, 30),
                date(2024, 3, 31),
            )
            if rng.random() < 0.06:
                s.last_balance_sheet_date = None
                s.last_income_statement_date = None
            else:
                bs = quarter_ends[int(rng.integers(0, len(quarter_ends)))]
                # Income statement usually matches; occasionally one quarter behind
                idx = quarter_ends.index(bs)
                inc_idx = min(idx + (1 if rng.random() < 0.08 else 0), len(quarter_ends) - 1)
                s.last_balance_sheet_date = bs
                s.last_income_statement_date = quarter_ends[inc_idx]
            if rng.random() < 0.18:
                s.latest_dividend_date = None
            else:
                # Dividend dates spread across 2014..2026 — some issuers haven't
                # paid in years (e.g. SARCO). Bias toward recent.
                year = int(rng.choice([2026, 2025, 2025, 2025, 2024, 2024, 2023, 2018, 2014]))
                month = int(rng.integers(1, 13))
                day = int(rng.integers(1, 28))
                s.latest_dividend_date = date(year, month, day)

            updated += 1

        db.commit()

    return updated


if __name__ == "__main__":
    n = seed()
    print(f"✓ analytics seeded for {n} stocks (full Tadawul universe)")
