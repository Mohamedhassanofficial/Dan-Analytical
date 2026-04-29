import { useEffect, useState } from "react";
import { Lightbulb, X } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useLabel } from "@/contexts/LabelsContext";

/**
 * Grouped filter modal — used for both the Risk-indicator group and the
 * Financial-indicator group (per PPTX slide 82: "=, <, > وغيرها" per
 * indicator).
 *
 * Clean rewrite (2026-04): the previous version coupled an enable-checkbox
 * to a disabled input, which made the whole control feel frozen until the
 * user clicked the box first. The new flow drops the checkbox entirely —
 * a row is "active" iff its value field is non-empty. Apply collects all
 * rows with a value and converts pct columns from user units (4 = 4%) to
 * the decimal unit the StockRow uses (0.04) so the comparison in
 * passesFilter sees matching scales.
 */

export type OpFilterOperator = "=" | "<" | ">" | "<=" | ">=";

export const OPERATORS: OpFilterOperator[] = [">=", "<=", "=", ">", "<"];

export interface OpFilter {
  key: string;
  op: OpFilterOperator;
  value: number;
}

export interface FilterableColumn {
  key: string;
  labelKey: string;
  /** "pct" columns are stored as decimals in the DB (0.04 = 4%). The
   *  modal accepts and displays the friendly percentage and converts
   *  to/from the decimal at apply/seed time. */
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

interface DraftRow {
  op: OpFilterOperator;
  value: string; // empty string = filter inactive for this row
}

function buildSeed(columns: FilterableColumn[], current: OpFilter[]): Record<string, DraftRow> {
  const out: Record<string, DraftRow> = {};
  for (const c of columns) {
    const existing = current.find((f) => f.key === c.key);
    if (!existing) {
      out[c.key] = { op: ">=", value: "" };
      continue;
    }
    // pct: stored as decimal (0.04) → display as percent (4). Round to 4 dp
    // to absorb the float drift Number() introduces on Decimal-encoded values.
    const display =
      c.fmt === "pct"
        ? String(Math.round(existing.value * 1_000_000) / 10_000)
        : String(existing.value);
    out[c.key] = { op: existing.op, value: display };
  }
  return out;
}

export default function IndicatorFilterModal({
  open, title, columns, current, onApply, onClose,
}: Props) {
  const { t } = useTranslation();
  const label = useLabel();

  const [draft, setDraft] = useState<Record<string, DraftRow>>(() => buildSeed(columns, current));

  // Reset the draft to whatever the parent currently holds whenever the
  // modal opens. Closing-without-apply discards local edits intentionally.
  useEffect(() => {
    if (open) setDraft(buildSeed(columns, current));
  }, [open, columns, current]);

  if (!open) return null;

  function update(key: string, patch: Partial<DraftRow>) {
    setDraft((prev) => ({ ...prev, [key]: { ...prev[key], ...patch } }));
  }

  function clearAll() {
    const next: Record<string, DraftRow> = {};
    for (const c of columns) next[c.key] = { op: ">=", value: "" };
    setDraft(next);
  }

  function apply() {
    const out: OpFilter[] = [];
    for (const c of columns) {
      const row = draft[c.key];
      if (!row || row.value === "") continue; // empty value = inactive
      const raw = parseFloat(row.value);
      if (!Number.isFinite(raw)) continue;
      // pct columns: user types "4" meaning 4%, store 0.04 to match the
      // decimal-encoded StockRow field that passesFilter compares against.
      const value = c.fmt === "pct" ? raw / 100 : raw;
      out.push({ key: c.key, op: row.op, value });
    }
    onApply(out);
    onClose();
  }

  const activeCount = Object.values(draft).filter((d) => d.value !== "").length;

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
              <tr className="text-muted">
                <th className="py-2 text-start">{label("screener.filter_indicator")}</th>
                <th className="py-2 w-28 text-start">{label("screener.filter_operator")}</th>
                <th className="py-2 w-40 text-start">{label("screener.filter_value")}</th>
              </tr>
            </thead>
            <tbody>
              {columns.map((c) => {
                const row = draft[c.key] ?? { op: ">=" as OpFilterOperator, value: "" };
                return (
                  <tr key={c.key} className="border-t border-brand-100">
                    <td className="py-2">{label(c.labelKey)}</td>
                    <td className="py-2">
                      <select
                        className="input h-8 py-1 text-xs"
                        value={row.op}
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
                          value={row.value}
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
          <button onClick={clearAll} className="btn-ghost">
            {label("screener.clear_filters_modal")}
          </button>
          <div className="flex items-center gap-2">
            <button onClick={onClose} className="btn-secondary">
              {t("common.cancel")}
            </button>
            <button onClick={apply} className="btn-primary">
              {label("screener.apply_filters")}
              {activeCount > 0 && (
                <span className="ms-1 rounded-full bg-white text-brand-900 px-2 py-0.5 text-xs">
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
