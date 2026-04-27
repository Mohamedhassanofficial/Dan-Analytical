import { NavLink } from "react-router-dom";
import {
  Briefcase,
  Calculator,
  ExternalLink,
  Home,
  LayoutDashboard,
  Settings,
  TrendingUp,
  User,
} from "lucide-react";
import BrandLogo from "./BrandLogo";
import { useLabel } from "@/contexts/LabelsContext";
import { useAuth } from "@/contexts/AuthContext";

/**
 * Sidebar nav — 7 items in the order Loay specified on slides 2 and 6:
 *   الرئيسية / رابط سوق تداول / عرض المحافظ الاستثمارية /
 *   المؤشرات الإرشادية لاختيار السهم المناسب /
 *   تحليل النسب المالية الرئيسية /
 *   لمحة مختصرة عن المالك / لوحة تحكم المعلومات
 *
 * Admin gear stays as a final item, hidden for non-admin users.
 *
 * `/optimize` and `/history` are not in the sidebar in this iteration; they
 * stay reachable by URL or via PortfolioDetails.
 */
const TADAWUL_URL = "https://www.saudiexchange.sa";

export default function Sidebar() {
  const label = useLabel();
  const { user } = useAuth();

  const linkClass = ({ isActive }: { isActive: boolean }) =>
    isActive ? "nav-link-active" : "nav-link";

  return (
    <aside className="fixed inset-y-0 start-0 z-30 hidden w-64 flex-col bg-navy px-4 py-6 text-white lg:flex">
      <div className="mb-8 flex items-center gap-2 rounded-lg bg-white/95 p-2">
        <BrandLogo size="md" />
      </div>

      <nav className="flex flex-1 flex-col gap-1">
        <NavLink to="/" end className={linkClass}>
          <Home size={18} />
          {label("nav.home")}
        </NavLink>
        {/* External link to the Tadawul exchange — opens in a new tab. */}
        <a
          href={TADAWUL_URL}
          target="_blank"
          rel="noopener noreferrer"
          className="nav-link"
        >
          <ExternalLink size={18} />
          {label("nav.tadawul_link")}
        </a>
        <NavLink to="/portfolios" className={linkClass}>
          <Briefcase size={18} />
          {label("nav.portfolios_view")}
        </NavLink>
        <NavLink to="/screener" className={linkClass}>
          <TrendingUp size={18} />
          {label("nav.stock_indicators")}
        </NavLink>
        <NavLink to="/screener" className={linkClass}>
          <Calculator size={18} />
          {label("nav.financial_ratios")}
        </NavLink>
        <NavLink to="/about" className={linkClass}>
          <User size={18} />
          {label("nav.about_owner")}
        </NavLink>
        <NavLink to="/dashboard" className={linkClass}>
          <LayoutDashboard size={18} />
          {label("nav.info_dashboard")}
        </NavLink>
        {user?.is_admin && (
          <NavLink to="/admin/config" className={linkClass}>
            <Settings size={18} />
            {label("nav.admin")}
          </NavLink>
        )}
      </nav>
    </aside>
  );
}
