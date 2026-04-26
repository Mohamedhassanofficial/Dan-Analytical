import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  ArrowLeft,
  BarChart3,
  Briefcase,
  Calendar,
  ChartLine,
  TrendingUp,
} from "lucide-react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { StocksAPI, type StockAnalytics } from "@/api/stocks";
import { ApiError } from "@/api/client";
import HeaderInfo from "@/components/HeaderInfo";
import { useLabel } from "@/contexts/LabelsContext";
import { useLocale } from "@/contexts/LocaleContext";
import { fmtNum, fmtPct } from "@/lib/format";

/**
 * Stock Analyze page — Loay slides 98-99 / 109-111.
 *
 * Mounted at /stocks/:ticker/analyze. Driven by GET /stocks/{ticker}/analytics
 * which returns the 14 indicators + 16 extended ratios + computed
 * support/resistance + return distribution + price history + stock-vs-index
 * pair series.
 */
export default function StockAnalyzePage() {
  const { ticker = "" } = useParams<{ ticker: string }>();
  const navigate = useNavigate();
  const { t } = useTranslation();
  const label = useLabel();
  const { locale } = useLocale();

  const [data, setData] = useState<StockAnalytics | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [varDays, setVarDays] = useState<number>(1);

  useEffect(() => {
    if (!ticker) return;
    StocksAPI.analytics(ticker)
      .then(setData)
      .catch((e: unknown) =>
        setError(e instanceof ApiError ? e.detail : t("errors.network")),
      );
  }, [ticker, t]);

  // Approximate VaR loss in SAR — VaR% × varDays^0.5 × last_price (per-share)
  const varLoss = useMemo(() => {
    if (!data || data.var_95_daily === null || data.last_price === null) return null;
    return data.var_95_daily * Math.sqrt(Math.max(varDays, 1)) * data.last_price;
  }, [data, varDays]);

  if (error) return <div className="badge-error w-fit">{error}</div>;
  if (!data) return <div className="text-muted">{t("common.loading")}</div>;

  const displayName =
    locale === "ar"
      ? data.name_ar || data.name_en || data.ticker_suffix
      : data.name_en || data.name_ar || data.ticker_suffix;

  return (
    <div className="flex flex-col gap-5">
      {/* Header */}
      <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <button
            className="btn-ghost mb-1 px-0"
            onClick={() => navigate("/screener")}
          >
            <ArrowLeft size={14} />
            {label("analyze.back_btn")}
          </button>
          <h1 className="text-2xl font-semibold text-brand-900">
            {label("analyze.title")} — {data.ticker_suffix}
          </h1>
          <p className="mt-1 text-sm text-muted">
            <span className="font-mono font-semibold">{data.symbol}</span>
            <span className="ms-2">{displayName}</span>
            {data.sector_code && (
              <span className="ms-2 text-brand-700">· {data.sector_code}</span>
            )}
          </p>
        </div>
      </div>

      {/* Six info blocks */}
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
        <Block
          titleKey="analyze.section_movement"
          icon={<TrendingUp size={18} />}
          rows={[
            {
              labelKey: "analyze.field_market_price",
              value: data.last_price !== null ? fmtNum(data.last_price, 2) : "—",
            },
            {
              labelKey: "analyze.field_avg_midpoint",
              value:
                data.avg_price_midpoint !== null
                  ? fmtNum(data.avg_price_midpoint, 2)
                  : "—",
            },
            {
              labelKey: "analyze.field_52w_high",
              value: data.week52_high !== null ? fmtNum(data.week52_high, 2) : "—",
            },
            {
              labelKey: "analyze.field_52w_low",
              value: data.week52_low !== null ? fmtNum(data.week52_low, 2) : "—",
            },
            {
              labelKey: "analyze.field_max_return",
              value:
                data.max_return_250d !== null ? fmtPct(data.max_return_250d, 2) : "—",
            },
            {
              labelKey: "analyze.field_min_return",
              value:
                data.min_return_250d !== null ? fmtPct(data.min_return_250d, 2) : "—",
              negative: data.min_return_250d !== null && data.min_return_250d < 0,
            },
          ]}
        />

        <Block
          titleKey="analyze.section_risk"
          icon={<BarChart3 size={18} />}
          rows={[
            { labelKey: "screener.col_var_1d", value: pctOrDash(data.var_95_daily) },
            { labelKey: "screener.col_sharp", value: numOrDash(data.sharp_ratio, 3) },
            { labelKey: "screener.col_beta", value: numOrDash(data.beta, 3) },
            { labelKey: "screener.col_daily_vol", value: pctOrDash(data.daily_volatility) },
            { labelKey: "screener.col_annual_vol", value: pctOrDash(data.annual_volatility) },
            {
              labelKey: "screener.col_risk_rank",
              valueNode: data.risk_ranking ? (
                <span className={rankingBadge(data.risk_ranking)}>
                  {label(`ranking.${rankingKey(data.risk_ranking)}`)}
                </span>
              ) : (
                "—"
              ),
            },
          ]}
        />

        <Block
          titleKey="analyze.section_financial"
          icon={<Briefcase size={18} />}
          rows={[
            { labelKey: "screener.col_pe", value: numOrDash(data.pe_ratio, 2) },
            { labelKey: "screener.col_mb", value: numOrDash(data.market_to_book, 2) },
            { labelKey: "screener.col_roe", value: pctOrDash(data.roe) },
            { labelKey: "screener.col_fcf", value: pctOrDash(data.fcf_yield) },
            { labelKey: "screener.col_leverage", value: numOrDash(data.leverage_ratio, 2) },
            { labelKey: "screener.col_eps", value: numOrDash(data.eps, 2) },
            { labelKey: "screener.col_div_yield", value: pctOrDash(data.dividend_yield) },
            { labelKey: "screener.col_div_rate", value: numOrDash(data.annual_dividend_rate, 2) },
          ]}
        />

        <Block
          titleKey="analyze.section_extras"
          icon={<ChartLine size={18} />}
          rows={[
            { labelKey: "ratio.current_ratio", value: numOrDash(data.current_ratio, 2) },
            { labelKey: "ratio.quick_ratio", value: numOrDash(data.quick_ratio, 2) },
            { labelKey: "ratio.cash_ratio", value: numOrDash(data.cash_ratio, 2) },
            {
              labelKey: "ratio.interest_coverage",
              value: numOrDash(data.interest_coverage_ratio, 2),
            },
            { labelKey: "ratio.asset_turnover", value: numOrDash(data.asset_turnover, 2) },
            { labelKey: "ratio.inventory_turnover", value: numOrDash(data.inventory_turnover, 2) },
            { labelKey: "ratio.roa", value: pctOrDash(data.roa) },
            { labelKey: "ratio.net_profit_margin", value: pctOrDash(data.net_profit_margin) },
            { labelKey: "ratio.gross_profit_margin", value: pctOrDash(data.gross_profit_margin) },
            { labelKey: "ratio.bvps", value: numOrDash(data.book_value_per_share, 2) },
            { labelKey: "ratio.revenue_per_share", value: numOrDash(data.revenue_per_share, 2) },
            { labelKey: "ratio.debt_to_market_cap", value: pctOrDash(data.debt_to_market_cap) },
          ]}
        />

        <Block
          titleKey="analyze.section_dates"
          icon={<Calendar size={18} />}
          rows={[
            {
              labelKey: "screener.col_balance_sheet_date",
              value: data.last_balance_sheet_date ?? "N/A",
            },
            {
              labelKey: "screener.col_income_statement_date",
              value: data.last_income_statement_date ?? "N/A",
            },
            {
              labelKey: "screener.col_dividend_date",
              value: data.latest_dividend_date ?? "N/A",
            },
            {
              labelKey: "analyze.field_support",
              value: data.support_price !== null ? fmtNum(data.support_price, 2) : "—",
            },
            {
              labelKey: "analyze.field_resistance",
              value: data.resistance_price !== null ? fmtNum(data.resistance_price, 2) : "—",
            },
            {
              labelKey: "analyze.field_midpoint",
              value: data.midpoint_price !== null ? fmtNum(data.midpoint_price, 2) : "—",
            },
          ]}
        />

        <Block
          titleKey="analyze.section_capm"
          icon={<TrendingUp size={18} />}
          rows={[
            {
              labelKey: "analyze.expected_annual",
              value:
                data.expected_annual_return !== null
                  ? fmtPct(data.expected_annual_return, 2)
                  : "—",
            },
            {
              labelKey: "analyze.expected_daily",
              value:
                data.expected_daily_return !== null
                  ? fmtPct(data.expected_daily_return, 4)
                  : "—",
            },
          ]}
          footer={
            <div className="mt-3 rounded-md border border-brand-200 bg-brand-50 p-2 text-xs">
              <div className="mb-2 font-semibold text-brand-900">
                {label("analyze.section_var")}
              </div>
              <div className="flex items-center gap-2">
                <label className="text-brand-800">
                  {label("analyze.var_days_label")}
                </label>
                <input
                  type="number"
                  className="input h-8 w-20 text-sm"
                  min={1}
                  max={252}
                  value={varDays}
                  onChange={(e) => setVarDays(Math.max(1, Number(e.target.value) || 1))}
                />
              </div>
              <div className="mt-2 text-brand-900">
                {label("analyze.var_loss_amount")}:{" "}
                <span className="font-semibold tabular-nums">
                  {varLoss !== null ? fmtNum(varLoss, 2) : "—"}
                </span>
              </div>
            </div>
          }
        />
      </div>

      {/* Three charts */}
      <div className="card flex flex-col gap-6 p-4">
        <h2 className="text-lg font-semibold text-brand-900">
          {label("analyze.section_charts")}
        </h2>

        {/* Probability distribution */}
        <ChartCard titleKey="analyze.chart_distribution">
          {data.return_distribution.length > 0 ? (
            <ResponsiveContainer width="100%" height={260}>
              <BarChart
                data={data.return_distribution.map((b) => ({
                  bucket: `${(b.lower * 100).toFixed(2)}%`,
                  freq: b.frequency_pct,
                }))}
              >
                <CartesianGrid strokeDasharray="3 3" stroke="#dbe3ee" />
                <XAxis dataKey="bucket" tick={{ fontSize: 10 }} interval={2} />
                <YAxis tick={{ fontSize: 11 }} unit="%" />
                <Tooltip
                  formatter={(v: number) => [`${v}%`, "freq"]}
                  contentStyle={{ fontSize: 12 }}
                />
                <Bar dataKey="freq" fill="#1f3a73" />
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <EmptyChart />
          )}
        </ChartCard>

        {/* Stock vs Index */}
        <ChartCard titleKey="analyze.chart_stock_vs_index">
          {data.stock_vs_index.length > 0 ? (
            <ResponsiveContainer width="100%" height={260}>
              <LineChart
                data={data.stock_vs_index.map((p) => ({
                  date: p.trade_date,
                  stock: p.stock_return * 100,
                  index: p.index_return !== null ? p.index_return * 100 : null,
                }))}
              >
                <CartesianGrid strokeDasharray="3 3" stroke="#dbe3ee" />
                <XAxis dataKey="date" tick={{ fontSize: 10 }} interval="preserveStartEnd" />
                <YAxis tick={{ fontSize: 11 }} unit="%" />
                <Tooltip
                  formatter={(v) => (typeof v === "number" ? `${v.toFixed(2)}%` : "—")}
                  contentStyle={{ fontSize: 12 }}
                />
                <Legend wrapperStyle={{ fontSize: 12 }} />
                <Line
                  type="monotone"
                  dataKey="stock"
                  stroke="#1f3a73"
                  strokeWidth={1.6}
                  dot={false}
                  name={data.ticker_suffix}
                />
                <Line
                  type="monotone"
                  dataKey="index"
                  stroke="#d4a437"
                  strokeWidth={1.4}
                  dot={false}
                  name={data.sector_code ?? "Index"}
                />
              </LineChart>
            </ResponsiveContainer>
          ) : (
            <EmptyChart />
          )}
        </ChartCard>

        {/* Support / Resistance line chart */}
        <ChartCard titleKey="analyze.chart_support_resistance">
          {data.price_history.length > 0 ? (
            <ResponsiveContainer width="100%" height={260}>
              <LineChart
                data={data.price_history.map((p) => ({
                  date: p.trade_date,
                  close: p.close,
                }))}
              >
                <CartesianGrid strokeDasharray="3 3" stroke="#dbe3ee" />
                <XAxis dataKey="date" tick={{ fontSize: 10 }} />
                <YAxis tick={{ fontSize: 11 }} domain={["auto", "auto"]} />
                <Tooltip
                  formatter={(v: number) => fmtNum(v, 2)}
                  contentStyle={{ fontSize: 12 }}
                />
                {data.support_price !== null && (
                  <ReferenceLine
                    y={data.support_price}
                    stroke="#21a36b"
                    strokeDasharray="4 4"
                    label={{ value: "Support", fontSize: 11, fill: "#21a36b" }}
                  />
                )}
                {data.resistance_price !== null && (
                  <ReferenceLine
                    y={data.resistance_price}
                    stroke="#d97a18"
                    strokeDasharray="4 4"
                    label={{ value: "Resistance", fontSize: 11, fill: "#d97a18" }}
                  />
                )}
                <Line
                  type="monotone"
                  dataKey="close"
                  stroke="#1f3a73"
                  strokeWidth={1.8}
                  dot={false}
                />
              </LineChart>
            </ResponsiveContainer>
          ) : (
            <EmptyChart />
          )}
        </ChartCard>
      </div>
    </div>
  );
}

/* ────────────────────────────────────────────────────────────────────────── */
/* Helpers + small subcomponents                                              */
/* ────────────────────────────────────────────────────────────────────────── */

function numOrDash(v: number | null, digits = 2): string {
  if (v === null || v === undefined) return "—";
  return fmtNum(v, digits);
}

function pctOrDash(v: number | null): string {
  if (v === null || v === undefined) return "—";
  return fmtPct(v, 2);
}

function rankingKey(r: string): string {
  switch (r) {
    case "Conservative":
      return "conservative";
    case "Moderately Conservative":
      return "moderate";
    case "Aggressive":
      return "aggressive";
    case "Very Aggressive":
      return "very_aggressive";
    default:
      return "unknown";
  }
}

function rankingBadge(r: string): string {
  switch (r) {
    case "Conservative":
      return "badge-risk-conservative";
    case "Moderately Conservative":
      return "badge-risk-moderate";
    case "Aggressive":
      return "badge-risk-aggressive";
    case "Very Aggressive":
      return "badge-risk-very-aggressive";
    default:
      return "text-muted";
  }
}

interface BlockRow {
  labelKey: string;
  value?: string;
  valueNode?: React.ReactNode;
  negative?: boolean;
}

function Block({
  titleKey,
  icon,
  rows,
  footer,
}: {
  titleKey: string;
  icon: React.ReactNode;
  rows: BlockRow[];
  footer?: React.ReactNode;
}) {
  const label = useLabel();
  return (
    <div className="card flex flex-col p-4">
      <div className="mb-3 flex items-center gap-2 border-b border-brand-100 pb-2">
        <span className="grid h-7 w-7 place-items-center rounded-md bg-brand-700 text-white">
          {icon}
        </span>
        <h3 className="text-sm font-semibold text-brand-900">{label(titleKey)}</h3>
      </div>
      <dl className="flex flex-col gap-1.5 text-sm">
        {rows.map((r) => (
          <div key={r.labelKey} className="flex items-center justify-between gap-2">
            <dt className="inline-flex items-center gap-1.5 text-muted">
              {label(r.labelKey)}
              <HeaderInfo labelKey={r.labelKey} />
            </dt>
            <dd
              className={`tabular-nums font-medium ${
                r.negative ? "cell-negative px-1.5 rounded" : "text-brand-900"
              }`}
            >
              {r.valueNode ?? r.value}
            </dd>
          </div>
        ))}
      </dl>
      {footer}
    </div>
  );
}

function ChartCard({
  titleKey,
  children,
}: {
  titleKey: string;
  children: React.ReactNode;
}) {
  const label = useLabel();
  return (
    <div className="rounded-lg border border-brand-200 bg-white p-3">
      <h4 className="mb-2 text-sm font-semibold text-brand-900">{label(titleKey)}</h4>
      {children}
    </div>
  );
}

function EmptyChart() {
  const { t } = useTranslation();
  return (
    <div className="grid h-40 place-items-center text-sm text-muted">
      {t("common.loading")}
    </div>
  );
}
