import { NavLink } from "react-router-dom";
import {
  Briefcase,
  GraduationCap,
  Home,
  LineChart,
  Settings,
  TrendingUp,
  User,
} from "lucide-react";
import BrandLogo from "./BrandLogo";
import { useLabel } from "@/contexts/LabelsContext";
import { useAuth } from "@/contexts/AuthContext";

/**
 * Sidebar nav — 7 items per Loay slide #2.
 *
 * Order (top → bottom):
 *   الرئيسية / الأسواق / الأسهم / المحافظ / التعليم / عن المالك / إدارة النظام
 *
 * `/optimize` and `/history` are not in the sidebar in this iteration; they
 * stay reachable by URL or via PortfolioDetails.
 */
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
        <NavLink to="/markets" className={linkClass}>
          <LineChart size={18} />
          {label("nav.markets")}
        </NavLink>
        <NavLink to="/screener" className={linkClass}>
          <TrendingUp size={18} />
          {label("nav.stocks")}
        </NavLink>
        <NavLink to="/portfolios" className={linkClass}>
          <Briefcase size={18} />
          {label("nav.portfolios")}
        </NavLink>
        <NavLink to="/education" className={linkClass}>
          <GraduationCap size={18} />
          {label("nav.education")}
        </NavLink>
        <NavLink to="/about" className={linkClass}>
          <User size={18} />
          {label("nav.about")}
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
