import { useEffect, useMemo, useState } from "react";
import { Lightbulb, X } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useLabel } from "@/contexts/LabelsContext";

/**
 * Grouped filter modal — used for BOTH the Risk-indicator group and the
 * Financial-indicator group (per PPTX slide 82: "=, <, > وغيرها" per indicator).
 *
 * The parent passes the column list (label key + data key); the user picks
 * which columns to filter, chooses a comparison operator, and enters a value.
 * "Apply" returns the active filters to the parent.
 */

export type OpFilterOperator = "=" | "<" | ">" | "<=" | ">=";

export const OPERATORS: OpFilterOperator[] = [">=", "<=", "=", ">", "<"];

export interface OpFilter {
  key: string;
  op: OpFilterOperator;
  value: number;
}

export interface FilterableColumn {
  key: string;       // matches StockRow field name (e.g. "pe_ratio")
  labelKey: string;  // ui_labels key (e.g. "screener.col_pe")
  /** "pct" columns are stored as decimals in the DB (0.04 = 4%). The
   *  modal accepts and displays the user-friendly percentage value
   *  (4) and converts to/from the decimal at apply/seed time so the
   *  passesFilter comparison sees matching units. */
  fmt?: "num" | "pct";
}

interface Props {
  open: boolean;
  title: string;
  columns: FilterableColumn[];
  current: OpFilter[];
  onApply: (filters: OpFilter[]) => void;
  onClose: () => void;
}

type DraftRow = {
  enabled: boolean;
  op: OpFilterOperator;
  value: string;  // string because empty state matters
};

export default function IndicatorFilterModal({
  open, title, columns, current, onApply, onClose,
}: Props) {
  const { t } = useTranslation();
  const label = useLabel();

  // Seed draft state from the current filter list each time we open.
  // pct columns: stored value is a decimal (0.04); display the friendly 4.
  const seed = useMemo<Record<string, DraftRow>>(() => {
    const out: Record<string, DraftRow> = {};
    for (const c of columns) {
      const existing = current.find((f) => f.key === c.key);
      const displayValue = existing
        ? (c.fmt === "pct" ? String(existing.value * 100) : String(existing.value))
        : "";
      out[c.key] = existing
        ? { enabled: true, op: existing.op, value: displayValue }
        : { enabled: false, op: ">=", value: "" };
    }
    return out;
  }, [columns, current]);

  const [draft, setDraft] = useState<Record<string, DraftRow>>(seed);

  useEffect(() => {
    if (open) setDraft(seed);
  }, [open, seed]);

  if (!open) return null;

  function update(key: string, patch: Partial<DraftRow>) {
    setDraft((d) => ({ ...d, [key]: { ...d[key], ...patch } }));
  }

  function clear() {
    const next: Record<string, DraftRow> = {};
    for (const c of columns) next[c.key] = { enabled: false, op: ">=", value: "" };
    setDraft(next);
  }

  function apply() {
    const out: OpFilter[] = [];
    for (const c of columns) {
      const d = draft[c.key];
      if (!d.enabled) continue;
      const raw = parseFloat(d.value);
      if (Number.isNaN(raw)) continue;
      // pct columns: user types "4" meaning 4%, store as 0.04 to match
      // the decimal-encoded ROE / yield / vol fields on the StockRow.
      const v = c.fmt === "pct" ? raw / 100 : raw;
      out.push({ key: c.key, op: d.op, value: v });
    }
    onApply(out);
    onClose();
  }

  const activeCount = Object.values(draft).filter((d) => d.enabled && d.value !== "").length;

  return (
    <div
      className="fixed inset-0 z-40 flex items-start justify-center bg-brand-900/40 backdrop-blur-sm p-4 pt-20"
      onClick={onClose}
    >
      <div
        className="w-full max-w-2xl rounded-xl bg-white shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between border-b border-brand-100 px-5 py-4">
          <h2 className="text-lg font-semibold text-brand-900">{title}</h2>
          <button onClick={onClose} className="btn-ghost p-1" aria-label="close">
            <X size={18} />
          </button>
        </div>

        {/* Body */}
        <div className="max-h-[60vh] overflow-y-auto px-5 py-4">
          {/* Help banner — Loay slide 6 */}
          <div className="mb-4 flex items-start gap-2 rounded-md border border-brand-200 bg-brand-50 p-3 text-sm">
            <Lightbulb size={18} className="mt-0.5 flex-none text-brand-700" />
            <div className="leading-snug text-brand-900">
              <div className="font-semibold">{label("filter_modal.help_title")}</div>
              <div className="mt-0.5 text-xs text-brand-800">
                {label("filter_modal.help_body")}
              </div>
            </div>
          </div>

          <table className="w-full text-sm">
            <thead>
              <tr className="text-muted text-start">
                <th className="w-8 py-2"></th>
                <th className="py-2 text-start">
                  {label("screener.filter_indicator")}
                </th>
                <th className="py-2 w-28 text-start">
                  {label("screener.filter_operator")}
                </th>
                <th className="py-2 w-40 text-start">
                  {label("screener.filter_value")}
                </th>
              </tr>
            </thead>
            <tbody>
              {columns.map((c) => {
                const d = draft[c.key];
                return (
                  <tr key={c.key} className="border-t border-brand-100">
                    <td className="py-2">
                      <input
                        type="checkbox"
                        checked={d.enabled}
                        onChange={(e) => update(c.key, { enabled: e.target.checked })}
                      />
                    </td>
                    <td className="py-2">{label(c.labelKey)}</td>
                    <td className="py-2">
                      <select
                        className="input h-8 py-1 text-xs"
                        value={d.op}
                        disabled={!d.enabled}
                        onChange={(e) => update(c.key, { op: e.target.value as OpFilterOperator })}
                      >
                        {OPERATORS.map((op) => (
                          <option key={op} value={op}>{op}</option>
                        ))}
                      </select>
                    </td>
                    <td className="py-2">
                      <div className="relative">
                        <input
                          type="number"
                          step="any"
                          className={`input h-8 py-1 text-xs ${c.fmt === "pct" ? "pe-7" : ""}`}
                          value={d.value}
                          disabled={!d.enabled}
                          placeholder={c.fmt === "pct" ? "4" : "0.5"}
                          onChange={(e) => update(c.key, { value: e.target.value })}
                        />
                        {c.fmt === "pct" && (
                          <span className="pointer-events-none absolute end-2 top-1/2 -translate-y-1/2 text-xs text-muted">
                            %
                          </span>
                        )}
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between border-t border-brand-100 px-5 py-3">
          <button className="btn-secondary" onClick={clear}>
            {label("screener.filter_clear_group")}
          </button>
          <div className="flex gap-2">
            <button className="btn-ghost" onClick={onClose}>
              {t("common.cancel")}
            </button>
            <button className="btn-primary" onClick={apply}>
              {label("screener.filter_apply")}
              {activeCount > 0 && (
                <span className="ms-2 rounded-full bg-white/20 px-2 py-0.5 text-xs">
                  {activeCount}
                </span>
              )}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
