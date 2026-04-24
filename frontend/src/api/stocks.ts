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
}

export const StocksAPI = {
  list: () => api<StockRow[]>("/stocks"),
};
