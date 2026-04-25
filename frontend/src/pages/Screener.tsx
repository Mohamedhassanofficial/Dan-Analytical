import { useEffect, useMemo, useState, type ChangeEvent } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate, useSearchParams } from "react-router-dom";
import { AlertTriangle, ArrowLeft, BarChart3, Check, CheckCircle2, Filter, Plus, Search, Shield, X } from "lucide-react";
import { StocksAPI, type StockRow } from "@/api/stocks";
import { PortfolioAPI, type SavedPortfolio } from "@/api/portfolio";
import { ApiError } from "@/api/client";
import DataSourcesFooter from "@/components/DataSourcesFooter";
import HeaderInfo from "@/components/HeaderInfo";
import IndicatorFilterModal, {
  type FilterableColumn,
  type OpFilter,
} from "@/components/IndicatorFilterModal";
import SectorAveragesPanel from "@/components/SectorAveragesPanel";
import { useLabel } from "@/contexts/LabelsContext";
import { useLocale } from "@/contexts/LocaleContext";
import { fmtNum, fmtPct } from "@/lib/format";

/**
 * Stock Screener — "تحليل أداء الأسهم واختيار أسهم المحفظة الاستثمارية"
 *
 * Two-group filter UX per PPTX slides 82-91:
 *   - 6 Risk indicators (β, σ_daily, σ_annual, Sharpe, VaR, Risk Ranking)
 *   - 8 Financial indicators (P/E, M/B, ROE, FCF Yield, Leverage, EPS, Div Yield, Div Rate)
 * Each group opens its own modal where the user picks indicators + comparison
 * operators (=, <, >, <=, >=). Text search, sector dropdown, add-to-portfolio,
 * and Analyze (stub) remain per-row.
 *
 * Sticky behavior: top header row + filter-buttons row; first two columns
 * (Symbol + Name) sticky-start; Actions column sticky-end. `inset-inline-*`
 * keeps the freeze correct in both RTL and LTR.
 *
 * Numeric coloring: every numeric cell routes through `numToneClass()`:
 *   positive → text-ink, zero/negative → text-danger bold, null → text-muted.
 */

const DRAFT_KEY = "tadawul.draft_portfolio";

// ── Column definitions ──────────────────────────────────────────────────────
// fmt: "num" = raw decimal, "pct" = decimal × 100 with %, "money" = 2-dp fixed
type CellFmt = "num" | "pct" | "money";

interface NumericCol {
  key: keyof StockRow;
  labelKey: string;
  fmt: CellFmt;
  digits?: number;
}

const RISK_COLS: NumericCol[] = [
  { key: "beta",              labelKey: "screener.col_beta",        fmt: "num", digits: 3 },
  { key: "capm_expected_return", labelKey: "screener.col_capm_return", fmt: "pct" },
  { key: "daily_volatility",  labelKey: "screener.col_daily_vol",   fmt: "pct" },
  { key: "annual_volatility", labelKey: "screener.col_annual_vol",  fmt: "pct" },
  { key: "sharp_ratio",       labelKey: "screener.col_sharp",       fmt: "num", digits: 3 },
  { key: "var_95_daily",      labelKey: "screener.col_var_1d",      fmt: "pct" },
];

// Disclosure-date columns — rendered after the financial group, before
// the sticky Actions cell. Loay's mockup labels them under "Financial Ratios".
const DISCLOSURE_DATE_COLS: { key: keyof StockRow; labelKey: string }[] = [
  { key: "last_balance_sheet_date",    labelKey: "screener.col_balance_sheet_date" },
  { key: "last_income_statement_date", labelKey: "screener.col_income_statement_date" },
  { key: "latest_dividend_date",       labelKey: "screener.col_dividend_date" },
];

const FINANCIAL_COLS: NumericCol[] = [
  { key: "pe_ratio",             labelKey: "screener.col_pe",         fmt: "num", digits: 2 },
  { key: "market_to_book",       labelKey: "screener.col_mb",         fmt: "num", digits: 2 },
  { key: "roe",                  labelKey: "screener.col_roe",        fmt: "pct" },
  { key: "fcf_yield",            labelKey: "screener.col_fcf",        fmt: "pct" },
  { key: "leverage_ratio",       labelKey: "screener.col_leverage",   fmt: "num", digits: 3 },
  { key: "eps",                  labelKey: "screener.col_eps",        fmt: "money" },
  { key: "dividend_yield",       labelKey: "screener.col_div_yield",  fmt: "pct" },
  { key: "annual_dividend_rate", labelKey: "screener.col_div_rate",   fmt: "money" },
];

const RISK_FILTER_COLS: FilterableColumn[] = RISK_COLS
  .filter((c) => c.key !== "risk_ranking") // risk_ranking is categorical
  .map((c) => ({ key: c.key as string, labelKey: c.labelKey }));
const FINANCIAL_FILTER_COLS: FilterableColumn[] = FINANCIAL_COLS.map((c) => ({
  key: c.key as string, labelKey: c.labelKey,
}));

// ── Numeric cell tone rule (accountant-style) ───────────────────────────────
// Per PPTX slide 91: positive = black ink, zero or negative = red text on
// a light-pink surface so the cell visually flags itself.
function numToneClass(v: number | null | undefined): string {
  if (v === null || v === undefined) return "text-muted";
  return v > 0 ? "text-ink" : "cell-negative";
}

function formatCell(v: number | null | undefined, col: NumericCol): string {
  if (v === null || v === undefined) return "—";
  if (col.fmt === "pct") return fmtPct(v, col.digits ?? 2);
  if (col.fmt === "money") return v.toFixed(col.digits ?? 2);
  return fmtNum(v, col.digits ?? 3);
}

// ── Risk Ranking badge (Excel-spec colors per slide 91) ─────────────────────
// "مسمى درجة المخاطر وكذلك تضليل مخاطر الألوان يجب أن تكون نفس ما هو مذكور في
// ملف اكسل" — green / yellow / orange / red. Sanctioned exception to the
// otherwise blue-only theme.
function rankingBadgeClass(rank: string | null | undefined): string {
  switch (rank) {
    case "Conservative":             return "badge-risk-conservative";
    case "Moderately Conservative":  return "badge-risk-moderate";
    case "Aggressive":               return "badge-risk-aggressive";
    case "Very Aggressive":          return "badge-risk-very-aggressive";
    default:                         return "text-muted";
  }
}

// ── OpFilter evaluator ─────────────────────────────────────────────────────
function passesFilter(row: StockRow, f: OpFilter): boolean {
  const v = row[f.key as keyof StockRow];
  if (typeof v !== "number") return false; // null / string → excluded by strict op
  switch (f.op) {
    case "=":  return Math.abs(v - f.value) < 1e-9;
    case "<":  return v < f.value;
    case ">":  return v > f.value;
    case "<=": return v <= f.value;
    case ">=": return v >= f.value;
  }
}

// ── localStorage draft portfolio ────────────────────────────────────────────
function readDraft(): string[] {
  try {
    const raw = localStorage.getItem(DRAFT_KEY);
    return raw ? (JSON.parse(raw) as string[]) : [];
  } catch { return []; }
}
function writeDraft(list: string[]): void {
  localStorage.setItem(DRAFT_KEY, JSON.stringify(list));
}

// ────────────────────────────────────────────────────────────────────────────
// Page
// ────────────────────────────────────────────────────────────────────────────
export default function ScreenerPage() {
  const { t } = useTranslation();
  const label = useLabel();
  const { locale } = useLocale();

  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const portfolioId = searchParams.get("portfolio");
  const portfolioIdNum = portfolioId ? Number(portfolioId) : null;

  const [rows, setRows] = useState<StockRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [textFilter, setTextFilter] = useState("");
  const [sectorFilter, setSectorFilter] = useState("");
  const [riskFilters, setRiskFilters] = useState<OpFilter[]>([]);
  const [financialFilters, setFinancialFilters] = useState<OpFilter[]>([]);

  const [riskModalOpen, setRiskModalOpen] = useState(false);
  const [financialModalOpen, setFinancialModalOpen] = useState(false);

  const [draft, setDraft] = useState<string[]>(() => readDraft());

  // Portfolio-context mode (URL ?portfolio=<id>): fetch the portfolio so we
  // can show its name in the banner and use its current holdings as the
  // "already added" source of truth (instead of the localStorage draft).
  const [portfolio, setPortfolio] = useState<SavedPortfolio | null>(null);
  const [addingTicker, setAddingTicker] = useState<string | null>(null);

  // Slide #7 Add modal — opens when the user clicks Add on a row in
  // portfolio-context mode. Stores the row being added so the modal can
  // render its details. `addedTicker` drives the post-confirm success toast.
  const [addPending, setAddPending] = useState<StockRow | null>(null);
  const [addedTicker, setAddedTicker] = useState<string | null>(null);

  useEffect(() => {
    StocksAPI.list()
      .then(setRows)
      .catch((e: unknown) => {
        setError(e instanceof ApiError ? e.detail : t("errors.network"));
        setRows([]);
      });
  }, [t]);

  useEffect(() => {
    if (portfolioIdNum === null) {
      setPortfolio(null);
      return;
    }
    PortfolioAPI.getOne(portfolioIdNum)
      .then(setPortfolio)
      .catch((e: unknown) => {
        setError(e instanceof ApiError ? e.detail : t("errors.network"));
        setPortfolio(null);
      });
  }, [portfolioIdNum, t]);

  // Set of tickers currently in the portfolio — so the Add button flips to
  // Check when that stock is already added via a previous visit.
  const inPortfolio = useMemo<Set<string>>(() => {
    if (!portfolio) return new Set();
    return new Set(portfolio.holdings.map((h) => h.ticker));
  }, [portfolio]);

  const sectors = useMemo(() => {
    if (!rows) return [];
    const set = new Set<string>();
    for (const r of rows) if (r.sector_code) set.add(r.sector_code);
    return [...set].sort((a, b) => a.localeCompare(b));
  }, [rows]);

  const filtered = useMemo(() => {
    if (!rows) return [];
    const q = textFilter.trim().toLowerCase();
    return rows.filter((r) => {
      if (q) {
        const hay = `${r.symbol} ${r.ticker_suffix} ${r.name_ar ?? ""} ${r.name_en ?? ""}`.toLowerCase();
        if (!hay.includes(q)) return false;
      }
      if (sectorFilter && r.sector_code !== sectorFilter) return false;
      for (const f of riskFilters) if (!passesFilter(r, f)) return false;
      for (const f of financialFilters) if (!passesFilter(r, f)) return false;
      return true;
    });
  }, [rows, textFilter, sectorFilter, riskFilters, financialFilters]);

  // Last update banner — newest last_price_date across visible rows
  const lastUpdate = useMemo(() => {
    if (!filtered.length) return null;
    let max: string | null = null;
    for (const r of filtered) {
      if (r.last_price_date && (max === null || r.last_price_date > max)) {
        max = r.last_price_date;
      }
    }
    return max;
  }, [filtered]);

  function clearAll() {
    setTextFilter("");
    setSectorFilter("");
    setRiskFilters([]);
    setFinancialFilters([]);
  }

  function toggleDraft(symbol: string) {
    const next = draft.includes(symbol)
      ? draft.filter((s) => s !== symbol)
      : [...draft, symbol];
    setDraft(next);
    writeDraft(next);
  }

  // Portfolio-context add/remove — talks to the backend directly instead of
  // the localStorage draft. Keeps the row icon's state synchronised with the
  // live portfolio.
  async function togglePortfolioHolding(row: StockRow) {
    if (portfolioIdNum === null) {
      toggleDraft(row.symbol);
      return;
    }
    setAddingTicker(row.ticker_suffix);
    try {
      const updated = inPortfolio.has(row.ticker_suffix)
        ? await PortfolioAPI.removeHolding(portfolioIdNum, row.ticker_suffix)
        : await PortfolioAPI.addHolding(portfolioIdNum, row.ticker_suffix);
      setPortfolio(updated);
    } catch (e) {
      setError(e instanceof ApiError ? e.detail : t("errors.network"));
    } finally {
      setAddingTicker(null);
    }
  }

  // Add button click — three branches:
  //   - standalone (no ?portfolio=): toggle the localStorage draft, no modal
  //   - portfolio-context, row already in portfolio: direct remove (no modal)
  //   - portfolio-context, row not yet in portfolio: open slide-#7 modal
  function onAddClick(row: StockRow) {
    if (portfolioIdNum === null) {
      toggleDraft(row.symbol);
      return;
    }
    if (inPortfolio.has(row.ticker_suffix)) {
      void togglePortfolioHolding(row);
      return;
    }
    setAddPending(row);
  }

  async function confirmAdd() {
    if (!addPending || portfolioIdNum === null) return;
    const ticker = addPending.ticker_suffix;
    setAddingTicker(ticker);
    try {
      const updated = await PortfolioAPI.addHolding(portfolioIdNum, ticker);
      setPortfolio(updated);
      setAddedTicker(ticker);
      setAddPending(null);
    } catch (e) {
      setError(e instanceof ApiError ? e.detail : t("errors.network"));
    } finally {
      setAddingTicker(null);
    }
  }

  // Auto-clear the success toast after 3s.
  useEffect(() => {
    if (!addedTicker) return;
    const id = setTimeout(() => setAddedTicker(null), 3000);
    return () => clearTimeout(id);
  }, [addedTicker]);

  const displayName = (r: StockRow) =>
    locale === "ar"
      ? r.name_ar || r.name_en || r.ticker_suffix
      : r.name_en || r.name_ar || r.ticker_suffix;
  const displayIndustry = (r: StockRow) =>
    locale === "ar"
      ? r.industry_ar || r.industry_en || "—"
      : r.industry_en || r.industry_ar || "—";

  const ALL_NUMERIC_COLS = [...RISK_COLS, ...FINANCIAL_COLS];

  return (
    <div className="flex flex-col gap-4">
      {/* Title + summary */}
      <div className="flex flex-col gap-2">
        <h1 className="text-2xl font-semibold text-brand-900">{label("screener.title")}</h1>
        <div className="flex flex-wrap items-center gap-3 text-sm text-muted">
          <span>
            {rows === null
              ? t("common.loading")
              : label("screener.summary", { total: rows.length, shown: filtered.length })}
          </span>
          {lastUpdate && (
            <span className="badge-info">
              {label("screener.last_update")}: {lastUpdate}
            </span>
          )}
        </div>
      </div>

      {error && <div className="badge-error w-fit">{error}</div>}

      {/* Portfolio-context banner (shown only when ?portfolio=<id> is set) */}
      {portfolio && (
        <div className="card flex flex-wrap items-center justify-between gap-3 border-brand-300 bg-brand-50 p-3">
          <div className="flex items-center gap-3 text-sm text-brand-900">
            <span className="badge-info">{label("screener.portfolio_context_label")}</span>
            <span className="font-semibold">{portfolio.name}</span>
            <span className="text-muted">
              · {label("screener.portfolio_context_count", { n: portfolio.holding_count })}
            </span>
          </div>
          <button
            className="btn-secondary h-8 px-3"
            onClick={() => navigate(`/portfolios/${portfolio.id}`)}
          >
            <ArrowLeft size={14} />
            {label("screener.portfolio_context_back")}
          </button>
        </div>
      )}

      {/* Toolbar */}
      <div className="card flex flex-wrap items-center gap-3 p-3">
        <div className="relative">
          <Search className="absolute top-1/2 start-3 -translate-y-1/2 text-muted" size={16} />
          <input
            className="input ps-9 w-64"
            placeholder={label("screener.search_placeholder")}
            value={textFilter}
            onChange={(e: ChangeEvent<HTMLInputElement>) => setTextFilter(e.target.value)}
          />
        </div>

        <select
          className="input w-44"
          value={sectorFilter}
          onChange={(e) => setSectorFilter(e.target.value)}
        >
          <option value="">{label("screener.filter_any")}</option>
          {sectors.map((s) => (
            <option key={s} value={s}>{s}</option>
          ))}
        </select>

        <button className="btn-secondary" onClick={() => setRiskModalOpen(true)}>
          <Shield size={16} />
          {label("screener.filter_risk_btn")}
          {riskFilters.length > 0 && (
            <span className="ms-1 rounded-full bg-brand-900 text-white px-2 py-0.5 text-xs">
              {riskFilters.length}
            </span>
          )}
        </button>

        <button className="btn-secondary" onClick={() => setFinancialModalOpen(true)}>
          <Filter size={16} />
          {label("screener.filter_financial_btn")}
          {financialFilters.length > 0 && (
            <span className="ms-1 rounded-full bg-brand-900 text-white px-2 py-0.5 text-xs">
              {financialFilters.length}
            </span>
          )}
        </button>

        <button className="btn-ghost" onClick={clearAll}>
          <X size={14} />
          {label("screener.clear_filters")}
        </button>
      </div>

      {/* Sector averages panel — Loay slide #83 */}
      <SectorAveragesPanel />

      {/* Success banner after Add modal confirms (auto-dismisses after 3s) */}
      {addedTicker && (
        <div className="badge-ok flex items-center gap-2 w-fit">
          <CheckCircle2 size={14} />
          {label("screener.add_modal_added", { ticker: addedTicker })}
        </div>
      )}

      {/* Draft portfolio summary */}
      {draft.length > 0 && (
        <div className="card flex items-center justify-between border-brand-300 bg-brand-50 p-3">
          <div className="text-sm text-brand-900">
            {label("screener.draft_summary", { n: draft.length })}
          </div>
          <div className="flex flex-wrap gap-1.5">
            {draft.slice(0, 10).map((s) => (
              <span key={s} className="badge-info">{s}</span>
            ))}
            {draft.length > 10 && <span className="badge-info">+{draft.length - 10}</span>}
          </div>
        </div>
      )}

      {/* Table */}
      <div className="card p-0 overflow-hidden">
        <div className="relative max-h-[75vh] overflow-auto">
          <table className="border-collapse text-sm" style={{ minWidth: `${120 * (ALL_NUMERIC_COLS.length + DISCLOSURE_DATE_COLS.length + 4)}px` }}>
            <thead>
              <tr>
                <ThSticky colIndex={0}>{label("screener.col_symbol")}</ThSticky>
                <ThSticky colIndex={1}>{label("screener.col_name")}</ThSticky>
                <Th>{label("screener.col_sector")}</Th>
                <Th>{label("screener.col_industry")}</Th>
                {RISK_COLS.map((c) => (
                  <Th key={c.key as string}>
                    <span className="inline-flex items-center gap-1.5">
                      {label(c.labelKey)}
                      <HeaderInfo labelKey={c.labelKey} />
                    </span>
                  </Th>
                ))}
                <Th>
                  <span className="inline-flex items-center gap-1.5">
                    {label("screener.col_risk_rank")}
                    <HeaderInfo labelKey="screener.col_risk_rank" />
                  </span>
                </Th>
                {FINANCIAL_COLS.map((c) => (
                  <Th key={c.key as string}>
                    <span className="inline-flex items-center gap-1.5">
                      {label(c.labelKey)}
                      <HeaderInfo labelKey={c.labelKey} />
                    </span>
                  </Th>
                ))}
                {DISCLOSURE_DATE_COLS.map((c) => (
                  <Th key={c.key}>
                    <span className="inline-flex items-center gap-1.5">
                      {label(c.labelKey)}
                      <HeaderInfo labelKey={c.labelKey} />
                    </span>
                  </Th>
                ))}
                <ThSticky colIndex={0} end>{label("screener.col_actions")}</ThSticky>
              </tr>
            </thead>

            <tbody>
              {filtered.map((r) => {
                const isAdded = portfolioIdNum !== null
                  ? inPortfolio.has(r.ticker_suffix)
                  : draft.includes(r.symbol);
                return (
                  <tr key={r.symbol} className="screener-row-hover border-b border-brand-100">
                    <TdSticky colIndex={0} className="font-mono font-semibold">
                      {r.symbol}
                    </TdSticky>
                    <TdSticky colIndex={1}>
                      <div className="flex flex-col">
                        <span className="font-medium text-brand-900">{displayName(r)}</span>
                        <span className="text-xs text-muted">{r.ticker_suffix}</span>
                      </div>
                    </TdSticky>
                    <td className="screener-cell text-ink">{r.sector_code ?? "—"}</td>
                    <td className="screener-cell text-ink">{displayIndustry(r)}</td>

                    {/* Risk indicators (except risk_ranking, which is separate) */}
                    {RISK_COLS.slice(0, -1).map((c) => {
                      const v = r[c.key] as number | null;
                      return (
                        <td
                          key={c.key as string}
                          className={`screener-cell text-right tabular-nums ${numToneClass(v)}`}
                        >
                          {formatCell(v, c)}
                        </td>
                      );
                    })}

                    {/* Risk Ranking badge */}
                    <td className="screener-cell">
                      {r.risk_ranking ? (
                        <span className={rankingBadgeClass(r.risk_ranking)}>
                          {label(`ranking.${rankingKey(r.risk_ranking)}`)}
                        </span>
                      ) : "—"}
                    </td>

                    {/* Financial indicators */}
                    {FINANCIAL_COLS.map((c) => {
                      const v = r[c.key] as number | null;
                      return (
                        <td
                          key={c.key as string}
                          className={`screener-cell text-right tabular-nums ${numToneClass(v)}`}
                        >
                          {formatCell(v, c)}
                        </td>
                      );
                    })}

                    {/* Disclosure dates */}
                    {DISCLOSURE_DATE_COLS.map((c) => {
                      const v = r[c.key] as string | null;
                      return (
                        <td
                          key={c.key}
                          className={`screener-cell text-right tabular-nums ${v ? "text-ink" : "text-muted"}`}
                        >
                          {v ?? "N/A"}
                        </td>
                      );
                    })}

                    {/* Actions */}
                    <TdSticky colIndex={0} end>
                      <div className="flex items-center justify-end gap-2">
                        <button
                          className={isAdded ? "btn-secondary h-8 px-2 py-0" : "btn-primary h-8 px-2 py-0"}
                          onClick={() => onAddClick(r)}
                          disabled={addingTicker === r.ticker_suffix}
                          title={isAdded ? label("screener.remove") : label("screener.add_to_portfolio")}
                        >
                          {isAdded ? <Check size={14} /> : <Plus size={14} />}
                          <span className="hidden lg:inline">
                            {isAdded ? label("screener.added") : label("screener.add")}
                          </span>
                        </button>
                        <button
                          className="btn-ghost h-8 px-2 py-0"
                          title={label("screener.analyze")}
                          disabled
                        >
                          <BarChart3 size={14} />
                          <span className="hidden lg:inline">{label("screener.analyze")}</span>
                        </button>
                      </div>
                    </TdSticky>
                  </tr>
                );
              })}

              {rows !== null && filtered.length === 0 && (
                <tr>
                  <td
                    colSpan={RISK_COLS.length + FINANCIAL_COLS.length + DISCLOSURE_DATE_COLS.length + 4}
                    className="py-10 text-center text-muted"
                  >
                    {label("screener.empty")}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Data sources & update periods footer (Loay slide) */}
      <DataSourcesFooter />

      {/* Filter modals */}
      <IndicatorFilterModal
        open={riskModalOpen}
        title={label("screener.filter_risk_title")}
        columns={RISK_FILTER_COLS}
        current={riskFilters}
        onApply={setRiskFilters}
        onClose={() => setRiskModalOpen(false)}
      />
      <IndicatorFilterModal
        open={financialModalOpen}
        title={label("screener.filter_financial_title")}
        columns={FINANCIAL_FILTER_COLS}
        current={financialFilters}
        onApply={setFinancialFilters}
        onClose={() => setFinancialModalOpen(false)}
      />

      {/* Slide-#7 Add modal */}
      {addPending && portfolio && (
        <AddToPortfolioModal
          row={addPending}
          portfolio={portfolio}
          stockName={displayName(addPending)}
          submitting={addingTicker === addPending.ticker_suffix}
          onConfirm={() => void confirmAdd()}
          onClose={() => setAddPending(null)}
        />
      )}
    </div>
  );
}

/* ────────────────────────────────────────────────────────────────────────── */
/* Slide-#7 "Add to portfolio" modal                                          */
/* ────────────────────────────────────────────────────────────────────────── */
interface AddModalProps {
  row: StockRow;
  portfolio: SavedPortfolio;
  stockName: string;
  submitting: boolean;
  onConfirm: () => void;
  onClose: () => void;
}

function AddToPortfolioModal({
  row, portfolio, stockName, submitting, onConfirm, onClose,
}: AddModalProps) {
  const { t } = useTranslation();
  const label = useLabel();
  const { locale } = useLocale();

  const moneyFmt = useMemo(
    () =>
      new Intl.NumberFormat(locale === "ar" ? "ar-SA" : "en-GB", {
        style: "currency",
        currency: "SAR",
        maximumFractionDigits: 0,
      }),
    [locale],
  );
  const amountText = portfolio.initial_capital
    ? moneyFmt.format(portfolio.initial_capital)
    : "—";

  return (
    <div
      className="fixed inset-0 z-40 flex items-center justify-center bg-brand-900/40 backdrop-blur-sm p-4"
      onClick={onClose}
    >
      <div
        className="w-full max-w-md rounded-xl bg-white shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-brand-100 px-5 py-4">
          <h2 className="text-lg font-semibold text-brand-900">
            {label("screener.add_modal_title")}
          </h2>
          <button onClick={onClose} className="btn-ghost p-1" aria-label="close">
            <X size={18} />
          </button>
        </div>

        <div className="flex flex-col gap-4 px-5 py-4 text-sm">
          <div className="rounded-lg border border-brand-200 bg-brand-50 p-3">
            <div className="text-xs font-medium uppercase tracking-wide text-muted">
              {label("screener.add_modal_stock")}
            </div>
            <div className="mt-1 flex items-baseline gap-2">
              <span className="font-mono text-base font-semibold text-brand-900">
                {row.ticker_suffix}
              </span>
              <span className="text-brand-900">— {stockName}</span>
            </div>
            {row.sector_code && (
              <div className="mt-1 text-xs text-muted">{row.sector_code}</div>
            )}
          </div>

          <div className="rounded-lg border border-brand-200 bg-brand-50 p-3">
            <div className="text-xs font-medium uppercase tracking-wide text-muted">
              {label("screener.add_modal_portfolio")}
            </div>
            <div className="mt-1 font-semibold text-brand-900">{portfolio.name}</div>
            <div className="mt-1 text-xs text-muted">
              {label("screener.add_modal_holdings", {
                n: portfolio.holding_count,
                amount: amountText,
              })}
            </div>
          </div>

          <div className="flex items-start gap-2 rounded-lg border border-brand-300 bg-brand-100 p-3 text-xs text-brand-900">
            <AlertTriangle size={16} className="mt-0.5 flex-none text-brand-700" />
            <span>{label("screener.add_modal_weight_notice")}</span>
          </div>
        </div>

        <div className="flex justify-end gap-2 border-t border-brand-100 px-5 py-3">
          <button type="button" className="btn-ghost" onClick={onClose}>
            {label("screener.add_modal_cancel")}
          </button>
          <button
            type="button"
            className="btn-primary"
            onClick={onConfirm}
            disabled={submitting}
          >
            {submitting ? t("common.loading") : label("screener.add_modal_confirm")}
          </button>
        </div>
      </div>
    </div>
  );
}

function rankingKey(ranking: string): string {
  switch (ranking) {
    case "Conservative":            return "conservative";
    case "Moderately Conservative": return "moderate";
    case "Aggressive":              return "aggressive";
    case "Very Aggressive":         return "very_aggressive";
    default:                        return "unknown";
  }
}

// ── Sticky / non-sticky cell primitives ────────────────────────────────────

interface StickyProps {
  colIndex: number;
  end?: boolean;
  children?: React.ReactNode;
}

const STICKY_OFFSETS = ["0px", "90px"];

function stickyStyle(colIndex: number, end: boolean): React.CSSProperties {
  if (end) return { insetInlineEnd: "0px" };
  return { insetInlineStart: STICKY_OFFSETS[colIndex] ?? "0px" };
}

function Th({ children }: { children?: React.ReactNode }) {
  return (
    <th className="screener-th sticky top-0 z-20 text-start">
      {children}
    </th>
  );
}

function ThSticky({ colIndex, end, children }: StickyProps) {
  return (
    <th
      className="screener-th sticky top-0 z-30 text-start"
      style={stickyStyle(colIndex, !!end)}
    >
      {children}
    </th>
  );
}

function TdSticky({
  colIndex, end, className = "", children,
}: StickyProps & { className?: string }) {
  return (
    <td
      className={`screener-cell sticky z-10 bg-white ${className}`}
      style={stickyStyle(colIndex, !!end)}
    >
      {children}
    </td>
  );
}
