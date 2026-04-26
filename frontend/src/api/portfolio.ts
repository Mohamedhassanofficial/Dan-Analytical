import { api, apiUrl } from "./client";
import { getAccessToken } from "@/lib/tokens";

export interface OptimizeRequest {
  tickers: string[];
  use_db_data?: boolean;
  lookback_days?: number;
  as_of?: string;
  expected_returns?: number[];
  cov_daily?: number[][];
  daily_returns?: number[][];
  risk_free_rate?: number;
  method?: "slsqp" | "qp";
  min_stock_sd?: number;
  apply_min_sd_constraint?: boolean;
  apply_return_floor?: boolean;
  allow_shorting?: boolean;
}

export interface OptimizeResponse {
  success: boolean;
  method: string;
  message: string;
  weights: Record<string, number>;
  sharpe: number;
  expected_return: number;
  volatility: number;
  sum_weights: number;
  risk_free_rate: number;
  min_stock_sd: number | null;
  tickers: string[];
  capm_expected_return: Record<string, number>;
  annual_volatility: Record<string, number>;
  beta: Record<string, number>;
  cov_daily: number[][] | null;
  run_id: number | null;
}

export interface FrontierPoint {
  target_return: number;
  volatility: number;
  weights: number[];
}

export interface FrontierResponse {
  tickers: string[];
  points: FrontierPoint[];
  tangency_return: number;
  tangency_volatility: number;
  tangency_weights: Record<string, number>;
}

export interface MetricsRequest {
  tickers: string[];
  weights: number[];
  risk_free_rate?: number;
  use_db_data?: boolean;
  expected_returns?: number[];
  cov_daily?: number[][];
  daily_returns?: number[][];
}

export interface MetricsResponse {
  sharpe: number;
  expected_return: number;
  volatility: number;
  sum_weights: number;
  risk_contribution: Record<string, number>;
  var_95_daily: number;
  var_95_10d: number;
  cvar_95_daily: number;
}

export interface PortfolioRun {
  id: number;
  run_at: string;
  method: string;
  risk_free_rate: number;
  expected_return: number | null;
  volatility: number | null;
  sharpe: number | null;
  var_95: number | null;
  success: boolean;
  weights: Record<string, number> | null;
}

// Saved-portfolio CRUD types (Loay slide 1)
export interface PortfolioHolding {
  ticker: string;
  weight: number;
  purchase_date: string | null;
  purchase_price: number | null;
}

export interface AddHoldingPayload {
  ticker: string;
  purchase_date?: string;
  purchase_price?: number;
}

export interface SavedPortfolio {
  id: number;
  name: string;
  description: string | null;
  initial_capital: number | null;
  target_loss_threshold: number | null;
  holdings: PortfolioHolding[];
  status: "active" | "inactive";
  holding_count: number;
  total_weight: number;
  needs_recompute: boolean | null;
  created_at: string;
  updated_at: string;
}

export interface CreatePortfolioPayload {
  name: string;
  initial_capital: number | null;
}

export interface UpdatePortfolioPayload {
  name?: string;
  description?: string;
  initial_capital?: number;
  target_loss_threshold?: number;
}

export interface ComputeWeightsPayload {
  method?: "slsqp" | "qp";
  risk_free_rate?: number;
  lookback_days?: number;
  apply_min_sd_constraint?: boolean;
  apply_return_floor?: boolean;
  allow_shorting?: boolean;
}

export interface ComputeWeightsResult {
  portfolio_id: number;
  run_id: number;
  success: boolean;
  method: string;
  message: string;
  sharpe: number;
  expected_return: number;
  volatility: number;
  risk_free_rate: number;
  weights: Record<string, number>;
  annual_volatility: Record<string, number>;
  beta: Record<string, number>;
  capm_expected_return: Record<string, number>;
}

export const PortfolioAPI = {
  optimize: (req: OptimizeRequest) =>
    api<OptimizeResponse>("/portfolio/optimize", { method: "POST", body: req }),

  frontier: (req: OptimizeRequest, nPoints = 50) =>
    api<FrontierResponse>(`/portfolio/frontier?n_points=${nPoints}`, {
      method: "POST",
      body: req,
    }),

  metrics: (req: MetricsRequest) =>
    api<MetricsResponse>("/portfolio/metrics", { method: "POST", body: req }),

  runs: (limit = 20) => api<PortfolioRun[]>(`/portfolio/runs?limit=${limit}`),

  // Saved-portfolio CRUD (Loay slide 1)
  listSaved: () => api<SavedPortfolio[]>("/portfolio/"),

  create: (payload: CreatePortfolioPayload) =>
    api<SavedPortfolio>("/portfolio/", {
      method: "POST",
      body: { ...payload, holdings: [] },
    }),

  update: (id: number, patch: UpdatePortfolioPayload) =>
    api<SavedPortfolio>(`/portfolio/${id}`, { method: "PATCH", body: patch }),

  remove: (id: number) =>
    api<void>(`/portfolio/${id}`, { method: "DELETE" }),

  // Holdings (per-stock) + compute weights (closes the "active" loop)
  addHolding: (id: number, payload: AddHoldingPayload) =>
    api<SavedPortfolio>(`/portfolio/${id}/holdings`, {
      method: "POST",
      body: payload,
    }),

  removeHolding: (id: number, ticker: string) =>
    api<SavedPortfolio>(`/portfolio/${id}/holdings/${encodeURIComponent(ticker)}`, {
      method: "DELETE",
    }),

  computeWeights: (id: number, payload: ComputeWeightsPayload = {}) =>
    api<ComputeWeightsResult>(`/portfolio/${id}/compute`, {
      method: "POST",
      body: payload,
    }),

  getOne: (id: number) =>
    api<SavedPortfolio>(`/portfolio/${id}`),

  reportPdfUrl: (runId: number, locale: "ar" | "en") =>
    // GET endpoint: we expose a URL plus a token the browser can attach via Authorization.
    // Since <a href> can't carry headers, callers use downloadReport() which fetches
    // the blob and triggers a local download.
    apiUrl(`/portfolio/runs/${runId}/report.pdf?locale=${locale}`),

  async downloadReport(runId: number, locale: "ar" | "en"): Promise<void> {
    const blob = await api<Blob>(`/portfolio/runs/${runId}/report.pdf?locale=${locale}`, {
      blob: true,
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `portfolio-run-${runId}-${locale}.pdf`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  },
};

/** For code-splitting-free import of the access token getter (used by <img> etc.). */
export const currentAccessToken = (): string | null => getAccessToken();
