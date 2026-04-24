import { api } from "./client";

export interface AdminConfigEntry {
  key: string;
  value: unknown;
  value_type: "number" | "string" | "bool" | "json";
  description_ar: string | null;
  description_en: string | null;
  updated_at: string;
}

export interface SectorUploadResult {
  filename: string;
  rows_seen: number;
  rows_inserted: number;
  rows_skipped: number;
  warnings: string[];
}

export const AdminAPI = {
  listConfig: () => api<AdminConfigEntry[]>("/admin/config"),

  updateConfig: (key: string, value: unknown) =>
    api<AdminConfigEntry>(`/admin/config/${encodeURIComponent(key)}`, {
      method: "PUT",
      body: { value },
    }),

  uploadSectorHistory: (file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    return api<SectorUploadResult>("/admin/upload/sector-history", {
      method: "POST",
      body: fd, // client.ts detects FormData and skips Content-Type/JSON.stringify
    });
  },

  triggerPriceRefresh: () =>
    api<{ stocks_processed: number; total_rows_added: number; failures: number }>(
      "/admin/refresh-prices",
      { method: "POST" },
    ),
};
