import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Check, Save } from "lucide-react";
import { AdminAPI, type AdminConfigEntry } from "@/api/admin";
import { ApiError } from "@/api/client";
import { useLocale } from "@/contexts/LocaleContext";

type DirtyMap = Record<string, string>; // key → raw string (unparsed)

export default function AdminConfigPage() {
  const { t } = useTranslation();
  const { locale } = useLocale();
  const [entries, setEntries] = useState<AdminConfigEntry[] | null>(null);
  const [dirty, setDirty] = useState<DirtyMap>({});
  const [saving, setSaving] = useState<string | null>(null);
  const [savedKey, setSavedKey] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    AdminAPI.listConfig()
      .then(setEntries)
      .catch((e: unknown) =>
        setError(e instanceof ApiError ? e.detail : t("errors.network")),
      );
  }, [t]);

  function onChange(key: string, value: string) {
    setDirty({ ...dirty, [key]: value });
    setSavedKey(null);
  }

  async function onSave(entry: AdminConfigEntry) {
    const raw = dirty[entry.key];
    if (raw === undefined) return;

    let parsed: unknown = raw;
    try {
      if (entry.value_type === "number") parsed = Number(raw);
      else if (entry.value_type === "bool") parsed = raw === "true";
      else if (entry.value_type === "json") parsed = JSON.parse(raw);
    } catch {
      setError(`Invalid JSON for ${entry.key}`);
      return;
    }

    setSaving(entry.key);
    setError(null);
    try {
      const updated = await AdminAPI.updateConfig(entry.key, parsed);
      setEntries((cur) =>
        cur ? cur.map((e) => (e.key === entry.key ? updated : e)) : cur,
      );
      const rest = { ...dirty };
      delete rest[entry.key];
      setDirty(rest);
      setSavedKey(entry.key);
    } catch (e) {
      setError(e instanceof ApiError ? e.detail : t("admin.config_update_failed"));
    } finally {
      setSaving(null);
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <div>
        <h1 className="text-2xl font-semibold text-navy">{t("admin.config_title")}</h1>
        <p className="mt-1 text-sm text-muted">{t("admin.config_subtitle")}</p>
      </div>

      {error && <div className="badge-red">{error}</div>}

      {entries === null ? (
        <p className="text-muted">{t("common.loading")}</p>
      ) : (
        <div className="card overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border text-left text-muted">
                <th className="py-2 w-48">{t("admin.config_key")}</th>
                <th className="py-2 w-56">{t("admin.config_value")}</th>
                <th className="py-2">{t("admin.config_description")}</th>
                <th className="py-2 w-24"></th>
              </tr>
            </thead>
            <tbody>
              {entries.map((e) => {
                const raw = dirty[e.key] ?? stringify(e.value, e.value_type);
                return (
                  <tr key={e.key} className="border-b border-border last:border-0 align-top">
                    <td className="py-3 font-mono text-xs">{e.key}</td>
                    <td className="py-3">
                      {e.value_type === "bool" ? (
                        <select
                          className="input"
                          value={raw}
                          onChange={(ev) => onChange(e.key, ev.target.value)}
                        >
                          <option value="true">true</option>
                          <option value="false">false</option>
                        </select>
                      ) : (
                        <input
                          className="input"
                          type={e.value_type === "number" ? "number" : "text"}
                          step="any"
                          value={raw}
                          onChange={(ev) => onChange(e.key, ev.target.value)}
                        />
                      )}
                    </td>
                    <td className="py-3 text-sm text-muted">
                      {locale === "ar" ? e.description_ar : e.description_en}
                    </td>
                    <td className="py-3 text-right">
                      <button
                        className="btn-primary"
                        disabled={saving === e.key || dirty[e.key] === undefined}
                        onClick={() => void onSave(e)}
                      >
                        {savedKey === e.key ? <Check size={14} /> : <Save size={14} />}
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
  );
}

function stringify(v: unknown, type: AdminConfigEntry["value_type"]): string {
  if (v == null) return "";
  if (type === "json") return JSON.stringify(v, null, 2);
  return String(v);
}
