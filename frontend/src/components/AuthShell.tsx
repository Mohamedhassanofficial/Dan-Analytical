import { TrendingUp } from "lucide-react";
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import LanguageSwitch from "./LanguageSwitch";

export default function AuthShell({ children }: { children: ReactNode }) {
  const { t } = useTranslation();
  return (
    <div className="min-h-screen bg-navy text-white flex flex-col">
      <header className="flex items-center justify-between px-6 py-4">
        <div className="flex items-center gap-3">
          <div className="grid h-9 w-9 place-items-center rounded-lg bg-brand-500">
            <TrendingUp size={20} strokeWidth={2.2} />
          </div>
          <div className="leading-tight">
            <p className="text-sm font-semibold">{t("app.name")}</p>
            <p className="text-xs text-white/60">Tadawul · Markowitz</p>
          </div>
        </div>
        <LanguageSwitch />
      </header>
      <div className="flex flex-1 items-center justify-center px-4 py-8">
        <div className="w-full max-w-md">
          <div className="rounded-2xl bg-white p-8 text-ink shadow-2xl">{children}</div>
          <p className="mt-6 text-center text-xs text-white/60">{t("app.tagline")}</p>
        </div>
      </div>
    </div>
  );
}
