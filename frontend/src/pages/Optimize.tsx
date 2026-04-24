import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  Legend,
} from "recharts";
import { ApiError } from "@/api/client";
import { PortfolioAPI, type OptimizeResponse } from "@/api/portfolio";
import { colorFor, fmtNum, fmtPct } from "@/lib/format";

export default function OptimizePage() {
  const { t } = useTranslation();
  const nav = useNavigate();

  const [tickersText, setTickersText] = useState(
    "2222.SR, 1120.SR, 7010.SR, 2010.SR, 6002.SR, 2270.SR",
  );
  const [method, setMethod] = useState<"slsqp" | "qp">("qp");
  const [lookback, setLookback] = useState<number>(1260);
  const [riskFree, setRiskFree] = useState<number | "">("");
  const [allowShorting, setAllowShorting] = useState(false);
  const [applyMinSd, setApplyMinSd] = useState(true);
  const [applyReturnFloor, setApplyReturnFloor] = useState(true);

  const [result, setResult] = useState<OptimizeResponse | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    setResult(null);
    const tickers = tickersText
      .split(/[\s,;\n]+/)
      .map((s) => s.trim())
      .filter(Boolean);

    try {
      const res = await PortfolioAPI.optimize({
        tickers,
        use_db_data: true,
        lookback_days: lookback,
        risk_free_rate: riskFree === "" ? undefined : Number(riskFree),
        method,
        allow_shorting: allowShorting,
        apply_min_sd_constraint: applyMinSd,
        apply_return_floor: applyReturnFloor,
      });
      setResult(res);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : t("errors.network"));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold text-navy">{t("optimize.title")}</h1>
      </div>

      <form className="card grid grid-cols-1 gap-4 md:grid-cols-2" onSubmit={onSubmit}>
        <div className="md:col-span-2">
          <label className="label" htmlFor="tickers">{t("optimize.tickers_label")}</label>
          <textarea
            id="tickers"
            rows={3}
            className="input"
            placeholder={t("optimize.tickers_placeholder")}
            value={tickersText}
            onChange={(e) => setTickersText(e.target.value)}
            required
          />
        </div>

        <div>
          <label className="label" htmlFor="method">{t("optimize.method_label")}</label>
          <select
            id="method"
            className="input"
            value={method}
            onChange={(e) => setMethod(e.target.value as "slsqp" | "qp")}
          >
            <option value="qp">{t("optimize.method_qp")}</option>
            <option value="slsqp">{t("optimize.method_slsqp")}</option>
          </select>
        </div>

        <div>
          <label className="label" htmlFor="lookback">{t("optimize.lookback_label")}</label>
          <input
            id="lookback"
            type="number"
            min={30}
            max={2520}
            className="input"
            value={lookback}
            onChange={(e) => setLookback(Number(e.target.value))}
          />
        </div>

        <div>
          <label className="label" htmlFor="rf">{t("optimize.risk_free_label")}</label>
          <input
            id="rf"
            type="number"
            step={0.0005}
            min={0}
            max={0.5}
            className="input"
            placeholder="0.0475"
            value={riskFree}
            onChange={(e) => setRiskFree(e.target.value === "" ? "" : Number(e.target.value))}
          />
        </div>

        <div className="flex flex-col gap-2 text-sm">
          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={applyMinSd}
              onChange={(e) => setApplyMinSd(e.target.checked)}
            />
            {t("optimize.apply_min_sd")}
          </label>
          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={applyReturnFloor}
              onChange={(e) => setApplyReturnFloor(e.target.checked)}
            />
            {t("optimize.apply_return_floor")}
          </label>
          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={allowShorting}
              onChange={(e) => setAllowShorting(e.target.checked)}
            />
            {t("optimize.allow_shorting")}
          </label>
        </div>

        {error && <div className="md:col-span-2 badge-red">{error}</div>}

        <div className="md:col-span-2 flex gap-3">
          <button type="submit" className="btn-primary" disabled={submitting}>
            {submitting ? t("optimize.running") : t("optimize.submit")}
          </button>
          <button type="button" className="btn-ghost" onClick={() => nav("/history")}>
            {t("nav.history")}
          </button>
        </div>
      </form>

      {result && <OptimizeResult result={result} />}
    </div>
  );
}

function OptimizeResult({ result }: { result: OptimizeResponse }) {
  const { t } = useTranslation();

  const rows = Object.entries(result.weights)
    .map(([ticker, weight]) => ({
      ticker,
      weight,
      beta: result.beta[ticker] ?? 0,
      mu: result.capm_expected_return[ticker] ?? 0,
      sigma: result.annual_volatility[ticker] ?? 0,
    }))
    .filter((r) => r.weight >= 1e-4)
    .sort((a, b) => b.weight - a.weight);

  return (
    <div className="flex flex-col gap-4">
      <div className="card">
        <h2 className="mb-1 text-lg font-semibold">{t("optimize.result_title")}</h2>
        <p className="text-xs text-muted">{result.method}</p>

        <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
          <Stat label={t("dashboard.sharpe")} value={fmtNum(result.sharpe, 4)} />
          <Stat label={t("dashboard.expected_return")} value={fmtPct(result.expected_return)} />
          <Stat label={t("dashboard.volatility")} value={fmtPct(result.volatility)} />
          <Stat label={t("dashboard.sum_weights")} value={fmtNum(result.sum_weights, 4)} />
        </div>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <div className="card">
          <h3 className="mb-2 text-sm font-semibold">{t("dashboard.allocation_title")}</h3>
          <ResponsiveContainer width="100%" height={260}>
            <PieChart>
              <Pie data={rows} dataKey="weight" nameKey="ticker" innerRadius={60} outerRadius={100}>
                {rows.map((_, i) => <Cell key={i} fill={colorFor(i)} />)}
              </Pie>
              <Tooltip formatter={(v: number) => fmtPct(v)} />
              <Legend />
            </PieChart>
          </ResponsiveContainer>
        </div>

        <div className="card">
          <h3 className="mb-2 text-sm font-semibold">{t("optimize.weights_header")}</h3>
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={rows} layout="vertical" margin={{ left: 10 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#eef2f6" />
              <XAxis type="number" tickFormatter={(v) => `${(v * 100).toFixed(0)}%`} />
              <YAxis dataKey="ticker" type="category" width={80} />
              <Tooltip formatter={(v: number) => fmtPct(v)} />
              <Bar dataKey="weight" fill="#305d9a" />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div className="card overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border text-left text-muted">
              <th className="py-2">Ticker</th>
              <th className="py-2">β</th>
              <th className="py-2">μ (CAPM)</th>
              <th className="py-2">σ (annual)</th>
              <th className="py-2">Weight</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.ticker} className="border-b border-border last:border-0">
                <td className="py-2 font-medium">{r.ticker}</td>
                <td className="py-2">{fmtNum(r.beta, 3)}</td>
                <td className="py-2">{fmtPct(r.mu)}</td>
                <td className="py-2">{fmtPct(r.sigma)}</td>
                <td className="py-2 font-semibold text-navy">{fmtPct(r.weight)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg bg-surface p-3">
      <div className="text-xs font-medium uppercase tracking-wide text-muted">{label}</div>
      <div className="mt-1 text-lg font-semibold text-navy">{value}</div>
    </div>
  );
}
