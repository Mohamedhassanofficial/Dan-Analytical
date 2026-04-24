import { useState } from "react";
import { useTranslation } from "react-i18next";
import { UploadCloud } from "lucide-react";
import { AdminAPI, type SectorUploadResult } from "@/api/admin";
import { ApiError } from "@/api/client";

export default function AdminUploadPage() {
  const { t } = useTranslation();
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [result, setResult] = useState<SectorUploadResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function onUpload() {
    if (!file) return;
    setUploading(true);
    setError(null);
    setResult(null);
    try {
      const r = await AdminAPI.uploadSectorHistory(file);
      setResult(r);
    } catch (e) {
      setError(e instanceof ApiError ? e.detail : t("errors.network"));
    } finally {
      setUploading(false);
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-2xl font-semibold text-navy">{t("nav.admin_upload")}</h1>

      <div className="card">
        <label className="block">
          <span className="label">Excel / CSV — columns: Sector Code, Date, Close</span>
          <input
            type="file"
            accept=".xlsx,.xls,.csv"
            className="mt-2 block w-full text-sm file:mr-4 file:rounded-md file:border-0 file:bg-navy file:px-4 file:py-2 file:text-white hover:file:bg-navy-light"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          />
        </label>

        <button
          className="btn-primary mt-4"
          disabled={!file || uploading}
          onClick={() => void onUpload()}
        >
          <UploadCloud size={16} />
          {uploading ? t("common.loading") : t("common.submit")}
        </button>

        {error && <div className="badge-red mt-4">{error}</div>}
        {result && (
          <div className="mt-4 space-y-1 text-sm">
            <p>
              <strong>{result.filename}</strong>: {result.rows_inserted} inserted,{" "}
              {result.rows_skipped} skipped, {result.rows_seen} seen.
            </p>
            {result.warnings.length > 0 && (
              <ul className="list-disc ps-5 text-brand-700">
                {result.warnings.map((w, i) => <li key={i}>{w}</li>)}
              </ul>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
