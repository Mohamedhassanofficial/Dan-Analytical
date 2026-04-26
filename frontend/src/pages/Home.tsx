import { useNavigate } from "react-router-dom";
import { BarChart3, Briefcase, Mail, Phone, Scale } from "lucide-react";
import HeaderInfo from "@/components/HeaderInfo";
import { useAuth } from "@/contexts/AuthContext";
import { useLabel } from "@/contexts/LabelsContext";
import { useLocale } from "@/contexts/LocaleContext";

/**
 * Home / 3-card landing — Loay slide #2.
 *
 * The first thing the user sees after login. Three entry-point cards:
 *   1. Create / view portfolios → /portfolios
 *   2. Analyse stocks + add to portfolio → /screener
 *   3. Compute weights + monitor performance → /portfolios (pick one → details)
 *
 * The chart-heavy "Comprehensive Dashboard" (slide 1's value-prop) lives at
 * /dashboard now — accessible via deep link or PortfolioDetails.
 */
export default function HomePage() {
  const label = useLabel();
  const { user } = useAuth();
  const { locale } = useLocale();
  const navigate = useNavigate();

  const userName =
    locale === "ar"
      ? user?.full_name_ar || user?.full_name_en || user?.email || ""
      : user?.full_name_en || user?.full_name_ar || user?.email || "";

  return (
    <div className="flex flex-col gap-5">
      {/* Welcome strip */}
      <div className="flex flex-col gap-1">
        <h1 className="text-2xl font-semibold text-brand-900">
          {label("home.welcome_back")}
        </h1>
      </div>

      {/* Admin info banner */}
      {user && (
        <div className="card flex flex-wrap items-center justify-between gap-3 border-brand-300 bg-navy px-4 py-3 text-white">
          <span className="text-sm font-semibold">
            {label("home.admin_info", { name: userName })}
          </span>
          <div className="flex flex-wrap items-center gap-4 text-xs text-white/85">
            <span className="inline-flex items-center gap-1.5">
              <Mail size={14} />
              {user.email}
            </span>
            <span className="inline-flex items-center gap-1.5">
              <Phone size={14} />
              {user.mobile}
            </span>
          </div>
        </div>
      )}

      {/* (i) info strip */}
      <div className="card flex items-start gap-3 border-brand-200 bg-brand-50 p-3 text-sm text-brand-900">
        <div className="grid h-9 w-9 flex-none place-items-center rounded-full bg-brand-100 text-brand-700">
          <span className="text-base font-bold">i</span>
        </div>
        <p className="leading-relaxed">{label("home.info_strip")}</p>
      </div>

      {/* The three cards */}
      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
        <ActionCard
          number={1}
          icon={<Briefcase size={28} />}
          titleKey="home.card1_title"
          descKey="home.card1_desc"
          explainerKey="home.card1_explainer"
          onOpen={() => navigate("/portfolios")}
        />
        <ActionCard
          number={2}
          icon={<BarChart3 size={28} />}
          titleKey="home.card2_title"
          descKey="home.card2_desc"
          explainerKey="home.card2_explainer"
          onOpen={() => navigate("/screener")}
        />
        <ActionCard
          number={3}
          icon={<Scale size={28} />}
          titleKey="home.card3_title"
          descKey="home.card3_desc"
          explainerKey="home.card3_explainer"
          onOpen={() => navigate("/portfolios")}
        />
      </div>
    </div>
  );
}

function ActionCard({
  number,
  icon,
  titleKey,
  descKey,
  explainerKey,
  onOpen,
}: {
  number: number;
  icon: React.ReactNode;
  titleKey: string;
  descKey: string;
  explainerKey: string;
  onOpen: () => void;
}) {
  const label = useLabel();
  return (
    <div className="card relative flex flex-col gap-3 p-5">
      {/* Number badge top-start */}
      <div className="absolute top-3 start-3 grid h-7 w-7 place-items-center rounded-full bg-brand-500 text-xs font-bold text-white shadow">
        {number}
      </div>
      {/* Per-card explainer (i) — top-end */}
      <div className="absolute top-3 end-3">
        <HeaderInfo labelKey={explainerKey} />
      </div>

      {/* Centered icon */}
      <div className="mx-auto mt-6 grid h-16 w-16 place-items-center rounded-2xl bg-brand-50 text-brand-700">
        {icon}
      </div>

      <h3 className="text-center text-base font-semibold leading-snug text-brand-900">
        {label(titleKey)}
      </h3>
      <p className="text-center text-sm text-muted">{label(descKey)}</p>

      <button className="btn-primary mt-2 w-full justify-center" onClick={onOpen}>
        {label("home.open_button")}
      </button>
    </div>
  );
}
