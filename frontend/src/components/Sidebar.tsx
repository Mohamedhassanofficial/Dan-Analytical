import { NavLink } from "react-router-dom";
import {
  LayoutDashboard,
  Filter,
  Wand2,
  Briefcase,
  History,
  Settings,
  Upload,
  TrendingUp,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { useAuth } from "@/contexts/AuthContext";

export default function Sidebar() {
  const { t } = useTranslation();
  const { user } = useAuth();

  const linkClass = ({ isActive }: { isActive: boolean }) =>
    isActive ? "nav-link-active" : "nav-link";

  return (
    <aside className="fixed inset-y-0 start-0 z-30 hidden w-64 flex-col bg-navy px-4 py-6 text-white lg:flex">
      <div className="mb-8 flex items-center gap-3">
        <div className="grid h-10 w-10 place-items-center rounded-lg bg-brand-500 text-white">
          <TrendingUp size={22} strokeWidth={2.2} />
        </div>
        <div className="leading-tight">
          <p className="text-sm font-semibold">{t("app.name")}</p>
          <p className="text-xs text-white/60">Tadawul</p>
        </div>
      </div>

      <nav className="flex flex-1 flex-col gap-1">
        <NavLink to="/" end className={linkClass}>
          <LayoutDashboard size={18} />
          {t("nav.dashboard")}
        </NavLink>
        <NavLink to="/screener" className={linkClass}>
          <Filter size={18} />
          {t("nav.screener")}
        </NavLink>
        <NavLink to="/optimize" className={linkClass}>
          <Wand2 size={18} />
          {t("nav.optimize")}
        </NavLink>
        <NavLink to="/portfolios" className={linkClass}>
          <Briefcase size={18} />
          {t("nav.portfolios")}
        </NavLink>
        <NavLink to="/history" className={linkClass}>
          <History size={18} />
          {t("nav.history")}
        </NavLink>

        {user?.is_admin && (
          <>
            <div className="mt-6 mb-1 px-3 text-xs uppercase tracking-wider text-white/40">
              {t("nav.admin")}
            </div>
            <NavLink to="/admin/config" className={linkClass}>
              <Settings size={18} />
              {t("nav.admin_config")}
            </NavLink>
            <NavLink to="/admin/upload" className={linkClass}>
              <Upload size={18} />
              {t("nav.admin_upload")}
            </NavLink>
          </>
        )}
      </nav>

      <footer className="mt-4 text-xs text-white/40">v0.3.0 · Phase B</footer>
    </aside>
  );
}
