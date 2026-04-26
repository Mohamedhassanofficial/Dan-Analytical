import { api } from "./client";

/**
 * Full screener row — all 14 indicators from PPTX slide 83.
 * Every numeric is `number | null`; the Screener renders `null` as "—"
 * via `numToneClass(null) → text-muted`.
 */
export interface StockRow {
  // Identity
  symbol: string;
  ticker_suffix: string;
  name_ar: string | null;
  name_en: string | null;
  industry_ar: string | null;
  industry_en: string | null;
  sector_code: string | null;

  // Risk indicators (6)
  beta: number | null;
  capm_expected_return: number | null;
  daily_volatility: number | null;
  annual_volatility: number | null;
  sharp_ratio: number | null;
  var_95_daily: number | null;
  risk_ranking: string | null;

  // Financial indicators (8)
  pe_ratio: number | null;
  market_to_book: number | null;
  roe: number | null;
  fcf_yield: number | null;
  leverage_ratio: number | null;
  eps: number | null;
  dividend_yield: number | null;
  annual_dividend_rate: number | null;

  // Price snapshot
  last_price: number | null;
  last_price_date: string | null;
  last_analytics_refresh: string | null;

  // Disclosure dates (Loay slide — Financial Ratios band)
  last_balance_sheet_date: string | null;
  last_income_statement_date: string | null;
  latest_dividend_date: string | null;
}

// Data sources & update periods footer (Loay slide — مصادر البيانات وفترات التحديث)
export interface DataSourceRange {
  id: string;
  date_from: string | null;
  date_to: string | null;
  source_name: string;
  source_url: string | null;
}

export interface DataSourcesPayload {
  stock_prices: DataSourceRange;
  sector_indices: DataSourceRange;
  last_update: DataSourceRange;
}

// Sector-level summary + averages (Loay slide 83)
export interface SectorSummary {
  sector_code: string;
  sector_name_ar: string;
  sector_name_en: string;
  stock_count: number;
}

export interface SectorAverages {
  sector_code: string;
  sector_name_ar: string;
  sector_name_en: string;
  stock_count: number;
  // Risk
  avg_beta: number | null;
  avg_capm_expected_return: number | null;
  avg_daily_volatility: number | null;
  avg_annual_volatility: number | null;
  avg_sharp_ratio: number | null;
  avg_var_95_daily: number | null;
  risk_ranking: string | null;
  // Financial
  avg_pe_ratio: number | null;
  avg_market_to_book: number | null;
  avg_roe: number | null;
  avg_fcf_yield: number | null;
  avg_leverage_ratio: number | null;
  avg_eps: number | null;
  avg_dividend_yield: number | null;
  avg_annual_dividend_rate: number | null;
}

// Stock Analyze page (Loay slides 98-99 / 109-111)
export interface ReturnDistributionBucket {
  lower: number;
  upper: number;
  frequency_pct: number;
}

export interface PricePoint {
  trade_date: string;
  close: number;
}

export interface ReturnPair {
  trade_date: string;
  stock_return: number;
  index_return: number | null;
}

export interface StockAnalytics {
  // Identity
  symbol: string;
  ticker_suffix: string;
  name_ar: string | null;
  name_en: string | null;
  sector_code: string | null;
  industry_ar: string | null;
  industry_en: string | null;
  // Movement
  last_price: number | null;
  last_price_date: string | null;
  week52_high: number | null;
  week52_low: number | null;
  avg_price_midpoint: number | null;
  min_return_250d: number | null;
  max_return_250d: number | null;
  // Risk
  beta: number | null;
  capm_expected_return: number | null;
  daily_volatility: number | null;
  annual_volatility: number | null;
  sharp_ratio: number | null;
  var_95_daily: number | null;
  risk_ranking: string | null;
  // Financial Ratios — 14 + 16
  pe_ratio: number | null;
  market_to_book: number | null;
  roe: number | null;
  fcf_yield: number | null;
  leverage_ratio: number | null;
  eps: number | null;
  dividend_yield: number | null;
  annual_dividend_rate: number | null;
  current_ratio: number | null;
  quick_ratio: number | null;
  cash_ratio: number | null;
  interest_coverage_ratio: number | null;
  asset_turnover: number | null;
  inventory_turnover: number | null;
  receivables_turnover: number | null;
  payables_turnover: number | null;
  roa: number | null;
  net_profit_margin: number | null;
  gross_profit_margin: number | null;
  book_value_per_share: number | null;
  revenue_per_share: number | null;
  debt_to_market_cap: number | null;
  cash_to_assets: number | null;
  receivables_to_assets: number | null;
  // Disclosure
  last_balance_sheet_date: string | null;
  last_income_statement_date: string | null;
  latest_dividend_date: string | null;
  // Support/Resistance + chart series
  support_price: number | null;
  resistance_price: number | null;
  midpoint_price: number | null;
  return_distribution: ReturnDistributionBucket[];
  price_history: PricePoint[];
  stock_vs_index: ReturnPair[];
  expected_annual_return: number | null;
  expected_daily_return: number | null;
}

export const StocksAPI = {
  list: () => api<StockRow[]>("/stocks"),
  sectorsSummary: () => api<SectorSummary[]>("/stocks/sectors-summary"),
  sectorAverages: (sectorCode: string) =>
    api<SectorAverages>(`/stocks/sector-averages?sector_code=${encodeURIComponent(sectorCode)}`),
  dataSources: () => api<DataSourcesPayload>("/stocks/data-sources"),
  analytics: (ticker: string) =>
    api<StockAnalytics>(`/stocks/${encodeURIComponent(ticker)}/analytics`),
};
