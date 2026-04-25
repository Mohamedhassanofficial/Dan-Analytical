import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type ChangeEvent,
  type FormEvent,
} from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import {
  BarChart3,
  FileText,
  MoreVertical,
  Pencil,
  Plus,
  Search,
  Trash2,
  X,
} from "lucide-react";
import { PortfolioAPI, type SavedPortfolio } from "@/api/portfolio";
import { ApiError } from "@/api/client";
import { useLabel } from "@/contexts/LabelsContext";
import { useLocale } from "@/contexts/LocaleContext";

/**
 * "محافظي" — Loay slide 1.
 *
 * Top-level actions: create portfolio, search by name, filter by status.
 * Row actions: select stocks (→ Screener), view details (stub), edit, delete.
 *
 * Status is derived server-side from holding weights (active iff holdings
 * exist AND sum of weights ≈ 1.0). The recompute banner shows when a PATCH
 * returns `needs_recompute:true`.
 */

type StatusFilter = "all" | "active" | "inactive";

export default function PortfolioListPage() {
  const { t } = useTranslation();
  const label = useLabel();
  const { locale } = useLocale();
  const nav = useNavigate();

  const [rows, setRows] = useState<SavedPortfolio[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [textFilter, setTextFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");

  const [modalMode, setModalMode] = useState<"create" | "edit" | null>(null);
  const [editingPortfolio, setEditingPortfolio] = useState<SavedPortfolio | null>(null);
  const [deletingPortfolio, setDeletingPortfolio] = useState<SavedPortfolio | null>(null);

  const [warning, setWarning] = useState<string | null>(null);
  const [openActionsFor, setOpenActionsFor] = useState<number | null>(null);

  const reload = async () => {
    try {
      const list = await PortfolioAPI.listSaved();
      setRows(list);
    } catch (e) {
      setError(e instanceof ApiError ? e.detail : t("errors.network"));
      setRows([]);
    }
  };

  useEffect(() => {
    void reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const filtered = useMemo(() => {
    if (!rows) return [];
    const q = textFilter.trim().toLowerCase();
    return rows.filter((p) => {
      if (q && !p.name.toLowerCase().includes(q)) return false;
      if (statusFilter !== "all" && p.status !== statusFilter) return false;
      return true;
    });
  }, [rows, textFilter, statusFilter]);

  const moneyFmt = useMemo(
    () =>
      new Intl.NumberFormat(locale === "ar" ? "ar-SA" : "en-GB", {
        style: "currency",
        currency: "SAR",
        maximumFractionDigits: 0,
      }),
    [locale],
  );

  const openCreate = () => {
    setEditingPortfolio(null);
    setModalMode("create");
  };
  const openEdit = (p: SavedPortfolio) => {
    setEditingPortfolio(p);
    setModalMode("edit");
    setOpenActionsFor(null);
  };

  const onSaved = async (saved: SavedPortfolio, mode: "create" | "edit") => {
    setModalMode(null);
    setEditingPortfolio(null);
    if (mode === "edit" && saved.needs_recompute) {
      setWarning(label("portfolios.warn_recompute"));
    }
    await reload();
  };

  const onDelete = async () => {
    if (!deletingPortfolio) return;
    try {
      await PortfolioAPI.remove(deletingPortfolio.id);
      setDeletingPortfolio(null);
      await reload();
    } catch (e) {
      setError(e instanceof ApiError ? e.detail : t("errors.network"));
    }
  };

  return (
    <div className="flex flex-col gap-5">
      {/* Title + breadcrumb */}
      <div>
        <h1 className="text-2xl font-semibold text-brand-900">
          {label("portfolios.title")}
        </h1>
        <p className="mt-1 text-sm text-muted">
          {label("portfolios.breadcrumb_home")} · {label("portfolios.breadcrumb_all")}
        </p>
      </div>

      {error && <div className="badge-error w-fit">{error}</div>}

      {warning && (
        <div className="card flex items-start justify-between gap-3 border-brand-300 bg-brand-50 p-3">
          <div className="text-sm text-brand-900">{warning}</div>
          <button
            onClick={() => setWarning(null)}
            className="btn-ghost p-1"
            aria-label="dismiss"
          >
            <X size={16} />
          </button>
        </div>
      )}

      {/* Toolbar */}
      <div className="card flex flex-wrap items-center gap-3 p-3">
        <button className="btn-primary" onClick={openCreate}>
          <Plus size={16} />
          {label("portfolios.create_btn")}
        </button>

        <div className="relative">
          <Search
            className="absolute top-1/2 start-3 -translate-y-1/2 text-muted"
            size={16}
          />
          <input
            className="input ps-9 w-64"
            placeholder={label("portfolios.search_placeholder")}
            value={textFilter}
            onChange={(e: ChangeEvent<HTMLInputElement>) => setTextFilter(e.target.value)}
          />
        </div>

        <select
          className="input w-40"
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value as StatusFilter)}
        >
          <option value="all">{label("portfolios.status_all")}</option>
          <option value="active">{label("portfolios.status_active")}</option>
          <option value="inactive">{label("portfolios.status_inactive")}</option>
        </select>
      </div>

      {/* Table */}
      <div className="card p-0 overflow-hidden">
        {rows === null ? (
          <div className="py-10 text-center text-muted">{t("common.loading")}</div>
        ) : filtered.length === 0 ? (
          <EmptyState onCreate={openCreate} />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-brand-200 bg-brand-50 text-start">
                  <th className="px-4 py-3 text-start text-xs font-semibold uppercase tracking-wide text-brand-800">
                    {label("portfolios.col_name")}
                  </th>
                  <th className="px-4 py-3 text-center text-xs font-semibold uppercase tracking-wide text-brand-800">
                    {label("portfolios.col_select")}
                  </th>
                  <th className="px-4 py-3 text-center text-xs font-semibold uppercase tracking-wide text-brand-800">
                    {label("portfolios.col_details")}
                  </th>
                  <th className="px-4 py-3 text-end text-xs font-semibold uppercase tracking-wide text-brand-800">
                    {label("portfolios.col_amount")}
                  </th>
                  <th className="px-4 py-3 text-center text-xs font-semibold uppercase tracking-wide text-brand-800">
                    {label("portfolios.col_status")}
                  </th>
                  <th className="px-4 py-3 text-center text-xs font-semibold uppercase tracking-wide text-brand-800 w-16">
                    {label("portfolios.col_actions")}
                  </th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((p) => (
                  <tr key={p.id} className="border-b border-brand-100 last:border-0 hover:bg-brand-50">
                    <td className="px-4 py-3 font-medium text-brand-900">{p.name}</td>

                    <td className="px-4 py-3 text-center">
                      <button
                        className="btn-ghost p-2"
                        title={label("portfolios.col_select")}
                        onClick={() => nav(`/screener?portfolio=${p.id}`)}
                      >
                        <BarChart3 size={18} className="text-brand-700" />
                      </button>
                    </td>

                    <td className="px-4 py-3 text-center">
                      <button
                        className="btn-ghost p-2"
                        title={label("portfolios.col_details")}
                        onClick={() => nav(`/portfolios/${p.id}`)}
                      >
                        <FileText size={18} className="text-brand-700" />
                      </button>
                    </td>

                    <td className="px-4 py-3 text-end tabular-nums text-ink">
                      {p.initial_capital != null
                        ? moneyFmt.format(p.initial_capital)
                        : "—"}
                    </td>

                    <td className="px-4 py-3 text-center">
                      {p.status === "active" ? (
                        <span className="badge-ok">
                          {label("portfolios.status_active")}
                        </span>
                      ) : (
                        <span className="badge-info">
                          {label("portfolios.status_inactive")}
                        </span>
                      )}
                    </td>

                    <td className="px-4 py-3 text-center">
                      <RowActions
                        open={openActionsFor === p.id}
                        onToggle={() =>
                          setOpenActionsFor((prev) => (prev === p.id ? null : p.id))
                        }
                        onEdit={() => openEdit(p)}
                        onDelete={() => {
                          setDeletingPortfolio(p);
                          setOpenActionsFor(null);
                        }}
                      />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Create / Edit modal */}
      {modalMode && (
        <PortfolioFormModal
          mode={modalMode}
          initial={editingPortfolio}
          onClose={() => {
            setModalMode(null);
            setEditingPortfolio(null);
          }}
          onSaved={onSaved}
          onError={(m) => setError(m)}
        />
      )}

      {/* Delete confirm */}
      {deletingPortfolio && (
        <ConfirmDialog
          title={label("portfolios.confirm_delete_title")}
          body={label("portfolios.confirm_delete_body")}
          confirmText={label("portfolios.action_delete")}
          cancelText={label("portfolios.cancel_btn")}
          onConfirm={onDelete}
          onCancel={() => setDeletingPortfolio(null)}
        />
      )}
    </div>
  );
}

/* ────────────────────────────────────────────────────────────────────────── */
/* Empty state                                                                 */
/* ────────────────────────────────────────────────────────────────────────── */
function EmptyState({ onCreate }: { onCreate: () => void }) {
  const label = useLabel();
  return (
    <div className="flex flex-col items-center gap-4 py-12 text-center text-muted">
      <div className="grid h-12 w-12 place-items-center rounded-full bg-brand-100 text-brand-600">
        <FileText size={22} />
      </div>
      <div>
        <p className="font-medium text-brand-900">{label("portfolios.empty_title")}</p>
        <p className="text-sm">{label("portfolios.empty_cta")}</p>
      </div>
      <button className="btn-primary" onClick={onCreate}>
        <Plus size={16} />
        {label("portfolios.create_btn")}
      </button>
    </div>
  );
}

/* ────────────────────────────────────────────────────────────────────────── */
/* Row actions popover                                                         */
/* ────────────────────────────────────────────────────────────────────────── */
interface RowActionsProps {
  open: boolean;
  onToggle: () => void;
  onEdit: () => void;
  onDelete: () => void;
}

function RowActions({ open, onToggle, onEdit, onDelete }: RowActionsProps) {
  const label = useLabel();
  const rootRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) {
        onToggle();
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open, onToggle]);

  return (
    <div className="relative inline-block" ref={rootRef}>
      <button
        className="btn-ghost p-1"
        onClick={onToggle}
        aria-label="actions"
      >
        <MoreVertical size={18} />
      </button>
      {open && (
        <div className="absolute end-0 top-full z-20 mt-1 min-w-[140px] overflow-hidden rounded-md border border-brand-200 bg-white shadow-card">
          <button
            className="flex w-full items-center gap-2 px-3 py-2 text-start text-sm text-brand-900 hover:bg-brand-50"
            onClick={onEdit}
          >
            <Pencil size={14} />
            {label("portfolios.action_edit")}
          </button>
          <button
            className="flex w-full items-center gap-2 px-3 py-2 text-start text-sm text-danger hover:bg-brand-50"
            onClick={onDelete}
          >
            <Trash2 size={14} />
            {label("portfolios.action_delete")}
          </button>
        </div>
      )}
    </div>
  );
}

/* ────────────────────────────────────────────────────────────────────────── */
/* Create / Edit modal                                                         */
/* ────────────────────────────────────────────────────────────────────────── */
interface FormModalProps {
  mode: "create" | "edit";
  initial: SavedPortfolio | null;
  onClose: () => void;
  onSaved: (p: SavedPortfolio, mode: "create" | "edit") => void | Promise<void>;
  onError: (m: string) => void;
}

function PortfolioFormModal({ mode, initial, onClose, onSaved, onError }: FormModalProps) {
  const { t } = useTranslation();
  const label = useLabel();

  const [name, setName] = useState(initial?.name ?? "");
  const [amount, setAmount] = useState<string>(
    initial?.initial_capital != null ? String(initial.initial_capital) : "",
  );
  const [submitting, setSubmitting] = useState(false);

  const title =
    mode === "create"
      ? label("portfolios.modal_create_title")
      : label("portfolios.modal_edit_title");
  const submitLabel =
    mode === "create"
      ? label("portfolios.create_submit")
      : label("portfolios.save_submit");

  async function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setSubmitting(true);
    try {
      const capital = amount === "" ? null : Number(amount);
      const saved =
        mode === "create"
          ? await PortfolioAPI.create({ name, initial_capital: capital })
          : await PortfolioAPI.update(initial!.id, {
              name: name !== initial!.name ? name : undefined,
              initial_capital: capital ?? undefined,
            });
      await onSaved(saved, mode);
    } catch (e) {
      onError(e instanceof ApiError ? e.detail : t("errors.network"));
    } finally {
      setSubmitting(false);
    }
  }

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
          <h2 className="text-lg font-semibold text-brand-900">{title}</h2>
          <button onClick={onClose} className="btn-ghost p-1" aria-label="close">
            <X size={18} />
          </button>
        </div>

        <form className="flex flex-col gap-4 px-5 py-4" onSubmit={onSubmit}>
          <div>
            <label className="label" htmlFor="portfolio_name">
              {label("portfolios.field_name")}
            </label>
            <input
              id="portfolio_name"
              className="input"
              required
              minLength={1}
              maxLength={255}
              placeholder={label("portfolios.field_name_example")}
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </div>
          <div>
            <label className="label" htmlFor="portfolio_amount">
              {label("portfolios.field_amount")}
            </label>
            <input
              id="portfolio_amount"
              className="input"
              type="number"
              min={0}
              step="100"
              placeholder={label("portfolios.field_amount_example")}
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
            />
          </div>

          <div className="mt-2 flex justify-end gap-2 border-t border-brand-100 pt-4">
            <button type="button" className="btn-ghost" onClick={onClose}>
              {label("portfolios.cancel_btn")}
            </button>
            <button type="submit" className="btn-primary" disabled={submitting}>
              {submitting ? t("common.loading") : submitLabel}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

/* ────────────────────────────────────────────────────────────────────────── */
/* Confirm dialog                                                              */
/* ────────────────────────────────────────────────────────────────────────── */
interface ConfirmProps {
  title: string;
  body: string;
  confirmText: string;
  cancelText: string;
  onConfirm: () => void | Promise<void>;
  onCancel: () => void;
}

function ConfirmDialog({ title, body, confirmText, cancelText, onConfirm, onCancel }: ConfirmProps) {
  return (
    <div
      className="fixed inset-0 z-40 flex items-center justify-center bg-brand-900/40 backdrop-blur-sm p-4"
      onClick={onCancel}
    >
      <div
        className="w-full max-w-sm rounded-xl bg-white shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="px-5 py-4">
          <h3 className="text-base font-semibold text-brand-900">{title}</h3>
          <p className="mt-2 text-sm text-muted">{body}</p>
        </div>
        <div className="flex justify-end gap-2 border-t border-brand-100 px-5 py-3">
          <button className="btn-ghost" onClick={onCancel}>
            {cancelText}
          </button>
          <button className="btn-danger" onClick={() => void onConfirm()}>
            {confirmText}
          </button>
        </div>
      </div>
    </div>
  );
}
