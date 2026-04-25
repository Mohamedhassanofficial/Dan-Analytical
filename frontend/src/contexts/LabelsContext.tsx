import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { useTranslation } from "react-i18next";
import { LabelsAPI, type UiLabel } from "@/api/labels";
import { useAuth } from "@/contexts/AuthContext";
import { useLocale } from "@/contexts/LocaleContext";

/**
 * Admin-editable labels layer.
 *
 * Every user-facing string has TWO sources:
 *   1. Admin-editable overrides in the `ui_labels` DB table (seeded via
 *      scripts/seed_ui_labels.py) — fetched here once the user is logged in.
 *   2. Static fallback in `src/i18n/{ar,en}.json` — always bundled, used
 *      when the DB has nothing for a key or when the user is not logged in.
 *
 * Components should use the `useLabel()` hook rather than calling `t()`
 * directly for any string the admin is expected to rename. Non-editable UI
 * strings (errors, tooltips, dev-only text) can keep using `t()`.
 */

type LabelMap = Record<string, UiLabel>;

interface LabelsContextValue {
  labels: LabelMap;
  loaded: boolean;
  refresh: () => Promise<void>;
}

const LabelsContext = createContext<LabelsContextValue | null>(null);

export function LabelsProvider({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  const [labels, setLabels] = useState<LabelMap>({});
  const [loaded, setLoaded] = useState(false);

  const refresh = useCallback(async () => {
    if (!user) {
      setLabels({});
      setLoaded(true);
      return;
    }
    try {
      const list = await LabelsAPI.list();
      const map: LabelMap = {};
      for (const l of list) map[l.key] = l;
      setLabels(map);
    } catch {
      // Silent fallback — the static i18n bundle covers us.
      setLabels({});
    } finally {
      setLoaded(true);
    }
  }, [user]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const value = useMemo(() => ({ labels, loaded, refresh }), [labels, loaded, refresh]);
  return <LabelsContext.Provider value={value}>{children}</LabelsContext.Provider>;
}

export function useLabelsContext(): LabelsContextValue {
  const ctx = useContext(LabelsContext);
  if (!ctx) throw new Error("useLabelsContext must be inside <LabelsProvider>");
  return ctx;
}

/**
 * Translate a key using admin overrides first, falling back to the static
 * i18n bundle. Placeholder interpolation mirrors react-i18next's `{{name}}`
 * syntax so overrides can reuse the same templates.
 */
export function useLabel(): (key: string, vars?: Record<string, string | number>) => string {
  const { labels } = useLabelsContext();
  const { locale } = useLocale();
  const { t } = useTranslation();

  return useCallback(
    (key: string, vars?: Record<string, string | number>) => {
      const override = labels[key];
      const raw = override
        ? locale === "ar"
          ? override.label_ar
          : override.label_en
        : null;

      const template = raw ?? t(key, vars);
      if (!vars || raw === null) return template;

      // Manual {{name}} interpolation when we used the override directly.
      return Object.entries(vars).reduce(
        (acc, [k, v]) => acc.replaceAll(`{{${k}}}`, String(v)),
        template,
      );
    },
    [labels, locale, t],
  );
}

/**
 * Long bilingual description for a label key (admin-editable). Returns null
 * when the description is missing, so callers can render the (i) icon
 * conditionally.
 */
export function useLabelDescription(): (key: string) => string | null {
  const { labels } = useLabelsContext();
  const { locale } = useLocale();
  return useCallback(
    (key: string) => {
      const l = labels[key];
      if (!l) return null;
      return (locale === "ar" ? l.description_ar : l.description_en) ?? null;
    },
    [labels, locale],
  );
}
