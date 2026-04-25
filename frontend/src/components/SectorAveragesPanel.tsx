import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Calculator, Filter, RefreshCw, Shield } from "lucide-react";
import {
  StocksAPI,
  type SectorAverages,
  type SectorSummary,
} from "@/api/stocks";
import { ApiError } from "@/api/client";
import { useLabel } from "@/contexts/LabelsContext";
import { useLocale } from "@/contexts/LocaleContext";
import { fmtNum, fmtPct } from "@/lib/format";

/**
 * Sector Averages Panel — Loay slide #83
 *
 *   "احتساب متوسط أداء القطاع الصناعي"
 *
 * User picks a sector → clicks "Risk averages" or "Financial averages" →
 * cards grid renders with the live AVERAGE of every indicator across the
 * stocks in that sector. Risk Ranking is derived from the averaged
 * annual_volatility per the slide-105 thresholds.
 *
 * Defaults: collapsed (just the picker + two buttons). Clicking a button
 * fetches and shows that group's cards.
 */

type Group = "risk" | "financial" | null;

// Accountant rule (matches Screener) — negative cells get pink background
function tone(v: number | null | undefined): string {
  if (v === null || v === undefined) return "text-muted";
  return v > 0 ? "text-ink" : "cell-negative";
}

// Excel-spec ranking colors per slide 91
function rankingClass(rank: string | null): string {
  switch (rank) {
    case "Conservative":            return "badge-risk-conservative";
    case "Moderately Conservative": return "badge-risk-moderate";
    case "Aggressive":              return "badge-risk-aggressive";
    case "Very Aggressive":         return "badge-risk-very-aggressive";
    default:                        return "text-muted";
  }
}

function rankingKey(r: string): string {
  switch (r) {
    case "Conservative":            return "conservative";
    case "Moderately Conservative": return "moderate";
    case "Aggressive":              return "aggressive";
    case "Very Aggressive":         return "very_aggressive";
    default:                        return "unknown";
  }
}

export default function SectorAveragesPanel() {
  const { t } = useTranslation();
  const label = useLabel();
  const { locale } = useLocale();

  const [sectors, setSectors] = useState<SectorSummary[]>([]);
  const [selectedSector, setSelectedSector] = useState<string>("");
  const [group, setGroup] = useState<Group>(null);
  const [averages, setAverages] = useState<SectorAverages | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Load sectors with stocks
  useEffect(() => {
    StocksAPI.sectorsSummary()
      .then((list) => {
        const withStocks = list.filter((s) => s.stock_count > 0);
        setSectors(withStocks);
      })
      .catch(() => setSectors([]));
  }, []);

  async function fetchAverages(sector: string) {
    if (!sector) return;
    setLoading(true);
    setError(null);
    try {
      const data = await StocksAPI.sectorAverages(sector);
      setAverages(data);
    } catch (e) {
      setError(e instanceof ApiError ? e.detail : t("errors.network"));
      setAverages(null);
    } finally {
      setLoading(false);
    }
  }

  function pickSector(s: string) {
    setSelectedSector(s);
    setAverages(null);
    if (s && group) void fetchAverages(s);
  }

  function pickGroup(g: Group) {
    setGroup(g);
    if (selectedSector && g) void fetchAverages(selectedSector);
  }

  const sectorLabel = (s: SectorSummary) =>
    locale === "ar"
      ? `${s.sector_name_ar} — ${label("sector_avg.count_suffix", { n: s.stock_count })}`
      : `${s.sector_name_en} — ${s.stock_count} stocks`;

  const sectorBanner = useMemo(() => {
    if (!averages) return null;
    const name = locale === "ar" ? averages.sector_name_ar : averages.sector_name_en;
    return `${name} — ${label("sector_avg.count_suffix", { n: averages.stock_count })}`;
  }, [averages, locale, label]);

  return (
    <div className="card flex flex-col gap-3 p-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm font-semibold text-brand-900">
          {label("sector_avg.title")}
        </span>
        <span className="text-xs text-muted">{label("sector_avg.subtitle")}</span>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <select
          className="input w-72"
          value={selectedSector}
          onChange={(e) => pickSector(e.target.value)}
        >
          <option value="">{label("sector_avg.pick_sector")}</option>
          {sectors.map((s) => (
            <option key={s.sector_code} value={s.sector_code}>
              {sectorLabel(s)}
            </option>
          ))}
        </select>

        <button
          className={
            group === "risk"
              ? "btn-primary"
              : "btn-secondary"
          }
          onClick={() => pickGroup("risk")}
          disabled={!selectedSector}
        >
          <Shield size={14} />
          {label("sector_avg.btn_risk")}
        </button>

        <button
          className={
            group === "financial"
              ? "btn-primary"
              : "btn-secondary"
          }
          onClick={() => pickGroup("financial")}
          disabled={!selectedSector}
        >
          <Filter size={14} />
          {label("sector_avg.btn_financial")}
        </button>

        {selectedSector && group && (
          <button
            className="btn-ghost"
            onClick={() => fetchAverages(selectedSector)}
            disabled={loading}
            title={label("sector_avg.refresh")}
          >
            <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
          </button>
        )}
      </div>

      {error && <div className="badge-error w-fit">{error}</div>}

      {averages && group && (
        <>
          <div className="text-xs text-brand-700">
            <Calculator size={12} className="inline-block me-1" />
            {sectorBanner}
          </div>

          {group === "risk" && (
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
              <Card label={label("screener.col_var_1d")} value={averages.avg_var_95_daily} fmt="pct" />
              <Card label={label("screener.col_sharp")} value={averages.avg_sharp_ratio} fmt="num" />
              <Card label={label("screener.col_beta")} value={averages.avg_beta} fmt="num" />
              <Card label={label("screener.col_daily_vol")} value={averages.avg_daily_volatility} fmt="pct" />
              <Card label={label("screener.col_annual_vol")} value={averages.avg_annual_volatility} fmt="pct" />
              <RankingCard
                label={label("screener.col_risk_rank")}
                ranking={averages.risk_ranking}
                rankingLabel={
                  averages.risk_ranking
                    ? label(`ranking.${rankingKey(averages.risk_ranking)}`)
                    : "—"
                }
              />
            </div>
          )}

          {group === "financial" && (
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-8">
              <Card label={label("screener.col_pe")} value={averages.avg_pe_ratio} fmt="num" digits={2} />
              <Card label={label("screener.col_roe")} value={averages.avg_roe} fmt="pct" />
              <Card label={label("screener.col_leverage")} value={averages.avg_leverage_ratio} fmt="num" digits={2} />
              <Card label={label("screener.col_fcf")} value={averages.avg_fcf_yield} fmt="pct" />
              <Card label={label("screener.col_mb")} value={averages.avg_market_to_book} fmt="num" digits={2} />
              <Card label={label("screener.col_eps")} value={averages.avg_eps} fmt="num" digits={2} />
              <Card label={label("screener.col_div_yield")} value={averages.avg_dividend_yield} fmt="pct" />
              <Card label={label("screener.col_div_rate")} value={averages.avg_annual_dividend_rate} fmt="num" digits={2} />
            </div>
          )}
        </>
      )}
    </div>
  );
}

function Card({
  label,
  value,
  fmt,
  digits,
}: {
  label: string;
  value: number | null;
  fmt: "num" | "pct";
  digits?: number;
}) {
  const display =
    value === null
      ? "—"
      : fmt === "pct"
        ? fmtPct(value, digits ?? 2)
        : fmtNum(value, digits ?? 3);
  return (
    <div className="rounded-lg border border-brand-200 bg-brand-50 p-3 text-center">
      <div className="text-xs font-medium text-brand-800">{label}</div>
      <div className={`mt-1 text-lg font-semibold tabular-nums ${tone(value)}`}>
        {display}
      </div>
    </div>
  );
}

function RankingCard({
  label,
  ranking,
  rankingLabel,
}: {
  label: string;
  ranking: string | null;
  rankingLabel: string;
}) {
  return (
    <div className="rounded-lg border border-brand-200 bg-brand-50 p-3 text-center">
      <div className="text-xs font-medium text-brand-800">{label}</div>
      <div className="mt-2">
        {ranking ? (
          <span className={rankingClass(ranking)}>{rankingLabel}</span>
        ) : (
          <span className="text-muted">—</span>
        )}
      </div>
    </div>
  );
}
