import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Download, FileText } from "lucide-react";
import { PortfolioAPI, type PortfolioRun } from "@/api/portfolio";
import { ApiError } from "@/api/client";
import { useLocale } from "@/contexts/LocaleContext";
import { fmtDateTime, fmtNum, fmtPct } from "@/lib/format";

export default function HistoryPage() {
  const { t } = useTranslation();
  const { locale } = useLocale();
  const [runs, setRuns] = useState<PortfolioRun[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [downloadingId, setDownloadingId] = useState<number | null>(null);

  useEffect(() => {
    PortfolioAPI.runs(50)
      .then(setRuns)
      .catch((e: unknown) => {
        setError(e instanceof ApiError ? e.detail : t("errors.network"));
        setRuns([]);
      });
  }, [t]);

  async function download(run: PortfolioRun) {
    setDownloadingId(run.id);
    try {
      await PortfolioAPI.downloadReport(run.id, locale);
    } catch (e) {
      setError(e instanceof ApiError ? e.detail : t("errors.network"));
    } finally {
      setDownloadingId(null);
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-2xl font-semibold text-navy">{t("history.title")}</h1>

      {error && <div className="badge-red">{error}</div>}

      {runs === null ? (
        <p className="text-muted">{t("common.loading")}</p>
      ) : runs.length === 0 ? (
        <div className="card text-center text-muted">
          <FileText className="mx-auto mb-3 text-muted" />
          {t("history.empty")}
        </div>
      ) : (
        <div className="card overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border text-left text-muted">
                <th className="py-2">{t("history.column_time")}</th>
                <th className="py-2">{t("history.column_method")}</th>
                <th className="py-2">{t("history.column_sharpe")}</th>
                <th className="py-2">{t("history.column_return")}</th>
                <th className="py-2">{t("history.column_volatility")}</th>
                <th className="py-2">{t("history.column_status")}</th>
                <th className="py-2" />
              </tr>
            </thead>
            <tbody>
              {runs.map((r) => (
                <tr key={r.id} className="border-b border-border last:border-0">
                  <td className="py-2">{fmtDateTime(r.run_at, locale)}</td>
                  <td className="py-2">{r.method}</td>
                  <td className="py-2">{r.sharpe != null ? fmtNum(r.sharpe, 4) : "—"}</td>
                  <td className="py-2">{r.expected_return != null ? fmtPct(r.expected_return) : "—"}</td>
                  <td className="py-2">{r.volatility != null ? fmtPct(r.volatility) : "—"}</td>
                  <td className="py-2">
                    {r.success ? (
                      <span className="badge-green">OK</span>
                    ) : (
                      <span className="badge-red">✗</span>
                    )}
                  </td>
                  <td className="py-2 text-right">
                    <button
                      className="btn-ghost"
                      onClick={() => void download(r)}
                      disabled={downloadingId === r.id}
                    >
                      <Download size={16} />
                      <span className="hidden sm:inline">{t("history.download_pdf")}</span>
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
