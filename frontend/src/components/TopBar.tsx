import { useTranslation } from "react-i18next";
import { LogOut, UserCircle2 } from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import { useLocale } from "@/contexts/LocaleContext";
import LanguageSwitch from "./LanguageSwitch";

/**
 * TopBar — Loay slide 2 marked the duplicate brand mark in the middle
 * of the header for removal ("حذف Logo"). The canonical DAN logo lives
 * in the sidebar now; the top bar carries language switch + signed-in
 * user info + logout only.
 */
export default function TopBar() {
  const { t } = useTranslation();
  const { user, logout } = useAuth();
  const { locale } = useLocale();

  const name =
    locale === "ar"
      ? user?.full_name_ar || user?.full_name_en || user?.email
      : user?.full_name_en || user?.full_name_ar || user?.email;

  return (
    <header className="sticky top-0 z-20 flex h-20 items-center justify-between border-b border-border bg-white/95 px-4 backdrop-blur sm:px-6">
      {/* start-edge spacer so justify-between still pushes controls to the end */}
      <div />

      <div className="flex items-center gap-3">
        <LanguageSwitch />
        {user && (
          <>
            <div className="hidden sm:flex items-center gap-2 rounded-lg bg-surface px-3 py-1.5 text-sm">
              <UserCircle2 size={18} className="text-muted" />
              <div className="leading-tight">
                <div className="text-xs text-muted">{t("common.signed_in_as")}</div>
                <div className="text-sm font-medium text-ink">{name}</div>
              </div>
            </div>
            <button onClick={logout} className="btn-ghost" aria-label={t("common.logout")}>
              <LogOut size={18} />
              <span className="hidden sm:inline">{t("common.logout")}</span>
            </button>
          </>
        )}
      </div>
    </header>
  );
}
