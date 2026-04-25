import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate, useParams } from "react-router-dom";
import {
  ArrowLeft,
  BarChart3,
  Calculator,
  Plus,
  Trash2,
  TrendingUp,
} from "lucide-react";
import {
  PortfolioAPI,
  type ComputeWeightsResult,
  type SavedPortfolio,
} from "@/api/portfolio";
import { ApiError } from "@/api/client";
import { useLabel } from "@/contexts/LabelsContext";
import { useLocale } from "@/contexts/LocaleContext";
import { fmtNum, fmtPct } from "@/lib/format";

/**
 * Portfolio Details — Loay slide #19.
 *
 * Shows the holdings of a saved portfolio plus a "احتساب الأوزان" button
 * that triggers Markowitz on the backend (POST /portfolio/{id}/compute) and
 * writes the optimal weights back into the holdings.
 *
 * Once compute succeeds, sum(weights) ≈ 1.0 → portfolio.status flips to
 * "active" (closes Loay's loop from slide #1).
 */

// Accountant-style numeric coloring (mirrors Screener) — negative cells get
// the cell-negative pink-background utility per PPTX slide 91.
function numToneClass(v: number | null | undefined): string {
  if (v === null || v === undefined) return "text-muted";
  return v > 0 ? "text-ink" : "cell-negative";
}

export default function PortfolioDetailsPage() {
  const { t } = useTranslation();
  const label = useLabel();
  const { locale } = useLocale();
  const navigate = useNavigate();
  const params = useParams();
  const portfolioId = Number(params.id);

  const [portfolio, setPortfolio] = useState<SavedPortfolio | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [computing, setComputing] = useState(false);
  const [removing, setRemoving] = useState<string | null>(null);
  const [lastCompute, setLastCompute] = useState<ComputeWeightsResult | null>(null);

  const reload = async () => {
    try {
      const p = await PortfolioAPI.getOne(portfolioId);
      setPortfolio(p);
      setLoadError(null);
    } catch (e) {
      setLoadError(e instanceof ApiError ? e.detail : t("errors.network"));
      setPortfolio(null);
    }
  };

  useEffect(() => {
    if (!Number.isFinite(portfolioId)) return;
    void reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [portfolioId]);

  const moneyFmt = useMemo(
    () =>
      new Intl.NumberFormat(locale === "ar" ? "ar-SA" : "en-GB", {
        style: "currency",
        currency: "SAR",
        maximumFractionDigits: 0,
      }),
    [locale],
  );

  async function onCompute() {
    if (!portfolio) return;
    setComputing(true);
    setError(null);
    setLastCompute(null);
    try {
      const result = await PortfolioAPI.computeWeights(portfolio.id, {
        method: "qp",
        apply_min_sd_constraint: false,
      });
      setLastCompute(result);
      await reload();
    } catch (e) {
      setError(e instanceof ApiError ? e.detail : t("errors.network"));
    } finally {
      setComputing(false);
    }
  }

  async function onRemoveHolding(ticker: string) {
    if (!portfolio) return;
    setRemoving(ticker);
    try {
      const updated = await PortfolioAPI.removeHolding(portfolio.id, ticker);
      setPortfolio(updated);
      setLastCompute(null); // weights now reset
    } catch (e) {
      setError(e instanceof ApiError ? e.detail : t("errors.network"));
    } finally {
      setRemoving(null);
    }
  }

  if (loadError) {
    return <div className="badge-error w-fit">{loadError}</div>;
  }
  if (!portfolio) {
    return <div className="text-muted">{t("common.loading")}</div>;
  }

  const totalAmount = portfolio.initial_capital ?? 0;

  return (
    <div className="flex flex-col gap-5">
      {/* Header */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <button
            className="btn-ghost mb-2 px-0"
            onClick={() => navigate("/portfolios")}
          >
            <ArrowLeft size={14} />
            {label("portfolios.title")}
          </button>
          <h1 className="text-2xl font-semibold text-brand-900">{portfolio.name}</h1>
          <p className="mt-1 text-sm text-muted">
            {label("details.breadcrumb")}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            className="btn-secondary"
            onClick={() => navigate(`/screener?portfolio=${portfolio.id}`)}
          >
            <Plus size={14} />
            {label("details.add_stocks")}
          </button>
          <button
            className="btn-primary"
            onClick={() => void onCompute()}
            disabled={computing || portfolio.holdings.length < 2}
            title={
              portfolio.holdings.length < 2
                ? label("details.compute_needs_2")
                : label("details.compute_btn")
            }
          >
            <Calculator size={14} />
            {computing ? t("common.loading") : label("details.compute_btn")}
          </button>
        </div>
      </div>

      {error && <div className="badge-error w-fit">{error}</div>}

      {/* Stat cards */}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Stat
          label={label("details.stat_amount")}
          value={moneyFmt.format(totalAmount)}
        />
        <Stat
          label={label("details.stat_holdings")}
          value={String(portfolio.holding_count)}
        />
        <Stat
          label={label("details.stat_status")}
          value={
            portfolio.status === "active"
              ? label("portfolios.status_active")
              : label("portfolios.status_inactive")
          }
          highlight={portfolio.status === "active"}
        />
        <Stat
          label={label("details.stat_total_weight")}
          value={fmtPct(portfolio.total_weight, 2)}
        />
      </div>

      {/* Compute results banner */}
      {lastCompute && (
        <div className="card grid grid-cols-1 gap-4 sm:grid-cols-3">
          <ResultStat
            label={label("dashboard.sharpe")}
            value={fmtNum(lastCompute.sharpe, 4)}
          />
          <ResultStat
            label={label("dashboard.expected_return")}
            value={fmtPct(lastCompute.expected_return, 2)}
          />
          <ResultStat
            label={label("dashboard.volatility")}
            value={fmtPct(lastCompute.volatility, 2)}
          />
        </div>
      )}

      {/* Holdings table */}
      <div className="card p-0 overflow-hidden">
        {portfolio.holdings.length === 0 ? (
          <div className="flex flex-col items-center gap-3 py-12 text-center text-muted">
            <div className="grid h-12 w-12 place-items-center rounded-full bg-brand-100 text-brand-600">
              <TrendingUp size={22} />
            </div>
            <p className="font-medium text-brand-900">
              {label("details.empty_title")}
            </p>
            <p className="text-sm">{label("details.empty_cta")}</p>
            <button
              className="btn-primary"
              onClick={() => navigate(`/screener?portfolio=${portfolio.id}`)}
            >
              <Plus size={16} />
              {label("details.add_stocks")}
            </button>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-brand-200 bg-brand-50">
                  <th className="px-4 py-3 text-start text-xs font-semibold uppercase tracking-wide text-brand-800">
                    {label("details.col_symbol")}
                  </th>
                  <th className="px-4 py-3 text-end text-xs font-semibold uppercase tracking-wide text-brand-800">
                    {label("details.col_weight")}
                  </th>
                  <th className="px-4 py-3 text-end text-xs font-semibold uppercase tracking-wide text-brand-800">
                    {label("details.col_position_amount")}
                  </th>
                  {lastCompute && (
                    <>
                      <th className="px-4 py-3 text-end text-xs font-semibold uppercase tracking-wide text-brand-800">
                        β
                      </th>
                      <th className="px-4 py-3 text-end text-xs font-semibold uppercase tracking-wide text-brand-800">
                        μ (CAPM)
                      </th>
                      <th className="px-4 py-3 text-end text-xs font-semibold uppercase tracking-wide text-brand-800">
                        σ
                      </th>
                    </>
                  )}
                  <th className="px-4 py-3 text-center text-xs font-semibold uppercase tracking-wide text-brand-800 w-16">
                    {label("portfolios.col_actions")}
                  </th>
                </tr>
              </thead>
              <tbody>
                {portfolio.holdings.map((h) => {
                  const positionAmount = totalAmount * h.weight;
                  return (
                    <tr key={h.ticker} className="border-b border-brand-100 last:border-0 hover:bg-brand-50">
                      <td className="px-4 py-3 font-mono font-semibold text-brand-900">
                        {h.ticker}
                      </td>
                      <td className={`px-4 py-3 text-end tabular-nums ${numToneClass(h.weight)}`}>
                        {fmtPct(h.weight, 2)}
                      </td>
                      <td className="px-4 py-3 text-end tabular-nums text-ink">
                        {moneyFmt.format(positionAmount)}
                      </td>
                      {lastCompute && (
                        <>
                          <td className={`px-4 py-3 text-end tabular-nums ${numToneClass(lastCompute.beta[h.ticker] ?? null)}`}>
                            {lastCompute.beta[h.ticker] !== undefined
                              ? fmtNum(lastCompute.beta[h.ticker], 3)
                              : "—"}
                          </td>
                          <td className={`px-4 py-3 text-end tabular-nums ${numToneClass(lastCompute.capm_expected_return[h.ticker] ?? null)}`}>
                            {lastCompute.capm_expected_return[h.ticker] !== undefined
                              ? fmtPct(lastCompute.capm_expected_return[h.ticker], 2)
                              : "—"}
                          </td>
                          <td className={`px-4 py-3 text-end tabular-nums ${numToneClass(lastCompute.annual_volatility[h.ticker] ?? null)}`}>
                            {lastCompute.annual_volatility[h.ticker] !== undefined
                              ? fmtPct(lastCompute.annual_volatility[h.ticker], 2)
                              : "—"}
                          </td>
                        </>
                      )}
                      <td className="px-4 py-3 text-center">
                        <button
                          className="btn-ghost p-1 text-danger"
                          onClick={() => void onRemoveHolding(h.ticker)}
                          disabled={removing === h.ticker}
                          title={label("portfolios.action_delete")}
                        >
                          <Trash2 size={16} />
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Compute footer hint */}
      {portfolio.holdings.length >= 2 && portfolio.status === "inactive" && !lastCompute && (
        <div className="card flex items-center gap-3 border-brand-300 bg-brand-50 p-3 text-sm text-brand-900">
          <BarChart3 size={18} className="text-brand-700" />
          {label("details.compute_hint")}
        </div>
      )}
    </div>
  );
}

function Stat({
  label,
  value,
  highlight = false,
}: {
  label: string;
  value: string;
  highlight?: boolean;
}) {
  return (
    <div className="stat-card">
      <span className="stat-label">{label}</span>
      <span className={highlight ? "stat-value text-brand-700" : "stat-value"}>
        {value}
      </span>
    </div>
  );
}

function ResultStat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg bg-brand-50 p-3">
      <div className="text-xs font-medium uppercase tracking-wide text-muted">{label}</div>
      <div className="mt-1 text-lg font-semibold text-brand-900">{value}</div>
    </div>
  );
}
