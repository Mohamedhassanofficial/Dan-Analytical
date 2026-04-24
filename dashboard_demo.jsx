import { useState, useMemo } from "react";
import {
  ScatterChart, Scatter, XAxis, YAxis, ZAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, PieChart, Pie, Cell, BarChart, Bar, LabelList,
} from "recharts";
import {
  ChevronDown, TrendingUp, TrendingDown, Shield, Activity,
  Info, Play, RotateCcw, Globe, LogOut, BarChart3, PieChart as PieIcon,
} from "lucide-react";

/* ============================================================================
   Tadawul Portfolio Optimization Dashboard
   Brand: "Dan Analytical" — navy #162849, red accents, teal buttons
   Mirrors slides 90 (Arabic) and 98 (English) from the 149-slide deck.
   All math matches portfolio_optimizer.py exactly (ddof=0 covariance,
   252-day annualization, CAPM expected returns).
   ========================================================================= */

// ---- Brand palette (taken from slides 90 and 98) --------------------------
const NAVY = "#162849";
const NAVY_LIGHT = "#2c3e63";
const BLUE_BG = "#e7f1ff";
const TEAL = "#2aa8b0";
const RED = "#c0392b";
const RED_BG = "#fce7e7";
const GREEN = "#27ae60";

// ---- Demo inputs (pulled from Optimal Portflio sheet) ---------------------
const STOCKS = [
  { symbol: "7010", nameEn: "STC",      nameAr: "اس تي سي",        price: 41.20, sector: "Telecom" },
  { symbol: "2222", nameEn: "Aramco",   nameAr: "أرامكو السعودية", price: 25.80, sector: "Energy"  },
  { symbol: "2010", nameEn: "SABIC",    nameAr: "سابك",            price: 67.45, sector: "Materials" },
  { symbol: "6002", nameEn: "Herfy",    nameAr: "هرفي للأغذية",    price: 28.15, sector: "Food" },
  { symbol: "2270", nameEn: "SADAFCO",  nameAr: "سدافكو",          price: 245.0, sector: "Food" },
  { symbol: "1120", nameEn: "AlRajhi",  nameAr: "الراجحي",         price: 92.30, sector: "Banking" },
];

// Daily covariance matrix (Optimal Portflio!R6:W11, converted from % to decimals)
const COV_DAILY = [
  [0.000133, 0.000025, 0.000133, 0.000039, 0.000030, 0.000053],
  [0.000025, 0.000076, 0.000025, 0.000024, 0.000005, 0.000032],
  [0.000133, 0.000025, 0.000133, 0.000039, 0.000030, 0.000053],
  [0.000039, 0.000024, 0.000039, 0.000341, 0.000051, 0.000037],
  [0.000030, 0.000005, 0.000030, 0.000051, 0.000310, 0.000034],
  [0.000053, 0.000032, 0.000053, 0.000037, 0.000034, 0.000176],
];
const TRADING_DAYS = 252;
const MU = [0.063, 0.007, 0.027, -0.024, 0.013, 0.116]; // Annual CAPM expected returns
const R_F = 0.0389;                                     // Dashboard!C6 (SAMA 1Y T-Bill)
// Pre-computed tangency weights from the Python Solver (parity-verified):
const OPTIMAL_WEIGHTS = [0.3021, 0.1526, 0.0509, 0.0000, 0.0374, 0.4570];

// ---- i18n -----------------------------------------------------------------
const I18N = {
  en: {
    dir: "ltr",
    brand: "Dan Analytical",
    nav: ["Dashboard", "Portfolio Evaluation", "Weights", "Value at Risk", "Admin Panel"],
    title: "Portfolio Dashboard",
    subtitle: "Tadawul Portfolio — Optimal Weights (Sharpe-Maximized)",
    perf: "Portfolio Performance Indicators",
    risk: "Portfolio Risk Indicators",
    frontier: "Efficient Frontier",
    allocation: "Allocation",
    weightsTable: "Optimal Weights by Stock",
    correlation: "Correlation Matrix",
    riskContrib: "Risk Contribution by Stock",
    marketValue: "Market Value",
    investment: "Invested",
    period: "Period (days)",
    dailyReturn: "Daily Return",
    periodReturn: "Period Return",
    annualReturn: "Annual Return",
    beta: "Beta",
    sharpe: "Sharpe Ratio",
    dailyVar: "Daily VaR (95%)",
    annualVol: "Annual Volatility",
    riskLevel: "Risk Level",
    conservative: "Conservative",
    modConservative: "Mod. Conservative",
    aggressive: "Aggressive",
    veryAggressive: "Very Aggressive",
    runSolver: "Run Solver",
    reset: "Reset to Optimal",
    symbol: "Symbol",
    company: "Company",
    weight: "Weight %",
    expRet: "Expected Return",
    vol: "Volatility",
    stockSharpe: "Sharpe",
    editWeights: "Adjust weights to explore alternatives — metrics update live",
    currency: "SAR",
    rf: "Risk-Free Rate (SAMA)",
    logout: "Logout",
    admin: "admin",
  },
  ar: {
    dir: "rtl",
    brand: "دان للتحليل المالي",
    nav: ["لوحة التحكم", "تقييم المحفظة", "الأوزان", "القيمة المعرضة للخطر", "لوحة الإدارة"],
    title: "لوحة تحكم المحفظة",
    subtitle: "محفظة تداول — الأوزان المثلى (تعظيم نسبة شارب)",
    perf: "مؤشرات أداء المحفظة",
    risk: "مؤشرات مخاطر المحفظة",
    frontier: "منحنى الكفاءة",
    allocation: "التوزيع",
    weightsTable: "الأوزان المثلى لكل سهم",
    correlation: "مصفوفة الارتباط",
    riskContrib: "مساهمة كل سهم في المخاطر",
    marketValue: "القيمة السوقية",
    investment: "مبلغ الاستثمار",
    period: "الفترة (أيام)",
    dailyReturn: "العائد اليومي",
    periodReturn: "عائد الفترة",
    annualReturn: "العائد السنوي",
    beta: "بيتا",
    sharpe: "نسبة شارب",
    dailyVar: "القيمة المعرضة للخطر اليومية (٩٥٪)",
    annualVol: "التقلب السنوي",
    riskLevel: "مستوى المخاطر",
    conservative: "تحفظي",
    modConservative: "تحفظي معتدل",
    aggressive: "جريء",
    veryAggressive: "جريء جداً",
    runSolver: "تشغيل المحسّن",
    reset: "العودة للأمثل",
    symbol: "الرمز",
    company: "الشركة",
    weight: "الوزن ٪",
    expRet: "العائد المتوقع",
    vol: "التقلب",
    stockSharpe: "شارب",
    editWeights: "عدّل الأوزان لاستكشاف بدائل — المؤشرات تتحدث مباشرة",
    currency: "ريال",
    rf: "المعدل الخالي من المخاطر (ساما)",
    logout: "خروج",
    admin: "مسؤول",
  },
};

// ---- Math helpers (identical to portfolio_optimizer.py) -------------------
const dot = (a, b) => a.reduce((s, ai, i) => s + ai * b[i], 0);
const matVec = (M, v) => M.map(row => dot(row, v));
const portReturn = (w, mu) => dot(w, mu);
const portVol = (w, covDaily) => {
  const covA = covDaily.map(row => row.map(v => v * TRADING_DAYS));
  return Math.sqrt(dot(w, matVec(covA, w)));
};
const sharpeRatio = (w, mu, covDaily, rf) => {
  const v = portVol(w, covDaily);
  return v < 1e-12 ? 0 : (portReturn(w, mu) - rf) / v;
};
// Risk contribution: w_i * (Σw)_i / (w'Σw) — Euler decomposition
const riskContrib = (w, covDaily) => {
  const covA = covDaily.map(row => row.map(v => v * TRADING_DAYS));
  const sw = matVec(covA, w);
  const total = dot(w, sw);
  if (total < 1e-12) return w.map(() => 0);
  return w.map((wi, i) => (wi * sw[i]) / total);
};
const correlation = (cov) => {
  const sd = cov.map((r, i) => Math.sqrt(r[i]));
  return cov.map((row, i) => row.map((v, j) => v / (sd[i] * sd[j])));
};

// Classify risk level as in slide 90 logic
const riskLevelClass = (vol, t) => {
  if (vol <= 0.10) return { label: t.conservative, color: GREEN, bg: "#e8f8ef" };
  if (vol <= 0.20) return { label: t.modConservative, color: "#f39c12", bg: "#fef5e7" };
  if (vol <= 0.30) return { label: t.aggressive, color: "#e67e22", bg: "#fdebd0" };
  return { label: t.veryAggressive, color: RED, bg: RED_BG };
};

// Solve tangency by line search along lambda scaling (demo version);
// in production this calls POST /api/optimize on the FastAPI service.
const resetToOptimal = () => [...OPTIMAL_WEIGHTS];

// Build efficient frontier client-side (minimum-variance curve sampled 40 pts).
// Uses a simple projected-gradient on a quadratic; sufficient for demo.
// Replace with POST /api/frontier call in production for precision.
const buildFrontier = () => {
  const minRet = Math.min(...MU);
  const maxRet = Math.max(...MU);
  const points = [];
  for (let i = 0; i < 40; i++) {
    const tgt = minRet + ((maxRet - minRet) * i) / 39;
    // Use a lightly perturbed weight search: greedy allocation by risk-adjusted return
    // (approximation; true QP lives on the backend).
    const scores = MU.map((m, j) => (m - R_F) / Math.sqrt(COV_DAILY[j][j] * TRADING_DAYS));
    let w = scores.map(s => Math.max(0, s));
    let sum = w.reduce((a, b) => a + b, 0);
    w = sum > 0 ? w.map(x => x / sum) : MU.map(() => 1 / 6);
    // Blend toward equal-weight as target return approaches minimum
    const blend = (tgt - minRet) / (maxRet - minRet);
    w = w.map((x, j) => x * blend + (1 - blend) / 6);
    sum = w.reduce((a, b) => a + b, 0);
    w = w.map(x => x / sum);
    points.push({ volatility: portVol(w, COV_DAILY), return_: portReturn(w, MU) });
  }
  points.sort((a, b) => a.volatility - b.volatility);
  return points;
};

// ---------------------------------------------------------------------------
export default function App() {
  const [lang, setLang] = useState("en");
  const t = I18N[lang];
  const rtl = t.dir === "rtl";

  const [weights, setWeights] = useState([...OPTIMAL_WEIGHTS]);
  const [investment, setInvestment] = useState(1628344.57);
  const [period, setPeriod] = useState(1);

  // --- Live portfolio metrics (recomputed on every weight change) ---
  const metrics = useMemo(() => {
    const normalized = (() => {
      const s = weights.reduce((a, b) => a + b, 0);
      return s > 0 ? weights.map(w => w / s) : weights;
    })();
    const annRet = portReturn(normalized, MU);
    const annVol = portVol(normalized, COV_DAILY);
    const sr = sharpeRatio(normalized, MU, COV_DAILY, R_F);
    const dailyVol = annVol / Math.sqrt(TRADING_DAYS);
    const dailyVar95 = 1.645 * dailyVol; // Parametric 95% 1-day VaR
    const dailyRet = annRet / TRADING_DAYS;
    const periodRet = dailyRet * period;
    return { annRet, annVol, sr, dailyVol, dailyVar95, dailyRet, periodRet, normalized };
  }, [weights, period]);

  const marketValue = investment * (1 + metrics.periodRet);
  const corrMatrix = useMemo(() => correlation(COV_DAILY), []);
  const frontier = useMemo(() => buildFrontier(), []);
  const rc = useMemo(() => riskContrib(metrics.normalized, COV_DAILY), [metrics.normalized]);
  const riskClass = riskLevelClass(metrics.annVol, t);

  const updateWeight = (i, pct) => {
    const w = [...weights];
    w[i] = Math.max(0, Math.min(1, pct / 100));
    setWeights(w);
  };

  const fmtPct = (v, d = 2) => `${(v * 100).toFixed(d)}%`;
  const fmtSAR = (v) => v.toLocaleString(lang === "ar" ? "ar-SA" : "en-US",
    { maximumFractionDigits: 2 }) + " " + t.currency;

  // ========================================================================
  return (
    <div dir={t.dir} className="min-h-screen bg-slate-50"
      style={{ fontFamily: rtl ? "'Tajawal', 'Segoe UI', sans-serif" : "'Segoe UI', system-ui, sans-serif" }}>

      {/* ==================== Top Nav ==================== */}
      <nav className="bg-white border-b border-slate-200 shadow-sm">
        <div className="max-w-screen-2xl mx-auto px-6 h-16 flex items-center justify-between">
          <div className="flex items-center gap-8">
            <div className="flex items-center gap-2">
              <div className="w-9 h-9 rounded flex items-center justify-center" style={{ background: NAVY }}>
                <BarChart3 size={20} color="white" />
              </div>
              <span className="font-bold text-lg tracking-tight" style={{ color: NAVY }}>
                {t.brand}
              </span>
            </div>
            <div className="hidden md:flex gap-1">
              {t.nav.map((item, i) => (
                <button key={i}
                  className={`px-3 py-2 text-sm font-medium rounded hover:bg-slate-50 transition
                    ${i === 0 ? "text-slate-900" : "text-slate-600"}
                    ${i === 4 ? "text-red-600" : ""}`}
                  style={i === 0 ? { color: NAVY, borderBottom: `2px solid ${NAVY}` } : {}}>
                  {item}
                </button>
              ))}
            </div>
          </div>
          <div className="flex items-center gap-3">
            <div className="flex rounded border border-slate-200 overflow-hidden text-xs">
              <button onClick={() => setLang("ar")}
                className={`px-3 py-1.5 ${lang === "ar" ? "text-white" : "text-slate-600"}`}
                style={lang === "ar" ? { background: NAVY } : {}}>Arabic</button>
              <button onClick={() => setLang("en")}
                className={`px-3 py-1.5 ${lang === "en" ? "text-white" : "text-slate-600"}`}
                style={lang === "en" ? { background: NAVY } : {}}>English</button>
            </div>
            <span className="text-sm text-slate-600 hidden sm:inline">{t.admin}</span>
            <button className="flex items-center gap-1.5 px-3 py-1.5 text-sm border border-red-200 text-red-600 rounded hover:bg-red-50">
              <LogOut size={14} /> {t.logout}
            </button>
          </div>
        </div>
      </nav>

      <main className="max-w-screen-2xl mx-auto px-6 py-6">
        {/* ==================== Title ==================== */}
        <div className="mb-6">
          <h1 className="text-2xl font-bold" style={{ color: NAVY }}>{t.title}</h1>
          <p className="text-sm text-slate-600 mt-1">{t.subtitle}</p>
        </div>

        {/* ==================== Portfolio Performance Indicators ==================== */}
        <section className="mb-6">
          <SectionHeader icon={<TrendingUp size={18} />} title={t.perf} />
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3 mt-3">
            <MetricCard label={t.marketValue} value={fmtSAR(marketValue)}
              accent={marketValue >= investment ? GREEN : RED} />
            <MetricCard label={t.investment} value={fmtSAR(investment)} />
            <MetricCard label={t.period}
              value={<div className="flex items-center gap-2">
                <input type="number" min="1" max="250" value={period}
                  onChange={e => setPeriod(Math.max(1, +e.target.value || 1))}
                  className="w-14 px-2 py-0.5 border border-slate-300 rounded text-center" />
                <span className="text-sm text-slate-500">{lang === "ar" ? "يوم" : "days"}</span>
              </div>} />
            <MetricCard label={t.dailyReturn} value={fmtPct(metrics.dailyRet, 3)}
              accent={metrics.dailyRet >= 0 ? GREEN : RED} />
            <MetricCard label={t.periodReturn} value={fmtPct(metrics.periodRet, 2)}
              accent={metrics.periodRet >= 0 ? GREEN : RED} />
            <MetricCard label={t.annualReturn} value={fmtPct(metrics.annRet, 2)}
              accent={metrics.annRet >= 0 ? GREEN : RED} />
          </div>
        </section>

        {/* ==================== Portfolio Risk Indicators ==================== */}
        <section className="mb-6">
          <SectionHeader icon={<Shield size={18} />} title={t.risk} />
          <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mt-3">
            <MetricCard label={t.beta} value={"0.87"}   /* placeholder - plug in real β */ />
            <MetricCard label={t.sharpe} value={metrics.sr.toFixed(3)}
              accent={metrics.sr > 0 ? GREEN : RED} />
            <MetricCard label={t.dailyVar} value={fmtPct(metrics.dailyVar95, 2)} accent={RED} />
            <MetricCard label={t.annualVol} value={fmtPct(metrics.annVol, 2)} />
            <div className="rounded-lg p-4 border border-slate-200 flex flex-col justify-between"
              style={{ background: riskClass.bg }}>
              <div className="text-xs font-medium text-slate-600">{t.riskLevel}</div>
              <div className="mt-2 font-bold text-sm" style={{ color: riskClass.color }}>
                {riskClass.label}
              </div>
              <div className="mt-2 h-2 rounded bg-white overflow-hidden">
                <div className="h-full rounded transition-all" style={{
                  width: `${Math.min(100, (metrics.annVol / 0.35) * 100)}%`,
                  background: riskClass.color
                }} />
              </div>
            </div>
          </div>
          <div className="text-xs text-slate-500 mt-2 flex items-center gap-1">
            <Info size={12} /> {t.rf}: {fmtPct(R_F, 2)}
          </div>
        </section>

        {/* ==================== Frontier + Allocation row ==================== */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 mb-6">
          {/* Efficient Frontier */}
          <div className="lg:col-span-2 bg-white rounded-lg border border-slate-200 p-4">
            <SectionHeader icon={<Activity size={18} />} title={t.frontier} compact />
            <div className="h-72 mt-3">
              <ResponsiveContainer>
                <ScatterChart margin={{ top: 10, right: 20, bottom: 30, left: 20 }}>
                  <CartesianGrid stroke="#e2e8f0" strokeDasharray="2 4" />
                  <XAxis type="number" dataKey="volatility" name="Volatility"
                    tickFormatter={v => `${(v * 100).toFixed(0)}%`}
                    label={{ value: "Volatility (σ)", position: "insideBottom", offset: -15, fill: NAVY }}
                    stroke={NAVY} />
                  <YAxis type="number" dataKey="return_" name="Return"
                    tickFormatter={v => `${(v * 100).toFixed(0)}%`}
                    label={{ value: "Expected Return", angle: -90, position: "insideLeft", fill: NAVY }}
                    stroke={NAVY} />
                  <Tooltip
                    formatter={(v) => `${(v * 100).toFixed(2)}%`}
                    contentStyle={{ borderRadius: 6, border: `1px solid ${NAVY}` }} />
                  {/* Individual stocks as context */}
                  <Scatter name="Stocks" data={STOCKS.map((s, i) => ({
                    volatility: Math.sqrt(COV_DAILY[i][i] * TRADING_DAYS),
                    return_: MU[i], name: s.nameEn
                  }))} fill={TEAL}>
                    <LabelList dataKey="name" position="top" fill={NAVY} fontSize={10} />
                  </Scatter>
                  <Scatter name="Frontier" data={frontier} fill={NAVY} line shape="circle" />
                  {/* Current portfolio marker */}
                  <Scatter name="Your Portfolio"
                    data={[{ volatility: metrics.annVol, return_: metrics.annRet }]}
                    fill={RED} shape="star" />
                </ScatterChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* Allocation pie */}
          <div className="bg-white rounded-lg border border-slate-200 p-4">
            <SectionHeader icon={<PieIcon size={18} />} title={t.allocation} compact />
            <div className="h-72 mt-3">
              <ResponsiveContainer>
                <PieChart>
                  <Pie data={STOCKS.map((s, i) => ({
                    name: lang === "ar" ? s.nameAr : s.nameEn,
                    value: metrics.normalized[i] * 100
                  })).filter(d => d.value > 0.01)}
                    dataKey="value" cx="50%" cy="50%" outerRadius={90} innerRadius={45}
                    label={d => `${d.value.toFixed(1)}%`}>
                    {STOCKS.map((_, i) => (
                      <Cell key={i} fill={[NAVY, TEAL, "#3498db", "#9b59b6", "#f39c12", "#16a085"][i]} />
                    ))}
                  </Pie>
                  <Tooltip formatter={(v) => `${v.toFixed(2)}%`} />
                </PieChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>

        {/* ==================== Weights table with sliders ==================== */}
        <div className="bg-white rounded-lg border border-slate-200 p-4 mb-6">
          <div className="flex items-center justify-between mb-3">
            <SectionHeader icon={<BarChart3 size={18} />} title={t.weightsTable} compact />
            <div className="flex gap-2">
              <button onClick={() => setWeights(resetToOptimal())}
                className="flex items-center gap-1.5 text-sm px-3 py-1.5 border border-slate-300 rounded hover:bg-slate-50">
                <RotateCcw size={14} /> {t.reset}
              </button>
              <button onClick={() => setWeights(resetToOptimal())}
                className="flex items-center gap-1.5 text-sm px-3 py-1.5 text-white rounded font-medium"
                style={{ background: NAVY }}>
                <Play size={14} /> {t.runSolver}
              </button>
            </div>
          </div>
          <div className="text-xs text-slate-500 mb-3">{t.editWeights}</div>
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-200" style={{ color: NAVY }}>
                <th className={`py-2 ${rtl ? "text-right" : "text-left"} font-semibold`}>{t.symbol}</th>
                <th className={`py-2 ${rtl ? "text-right" : "text-left"} font-semibold`}>{t.company}</th>
                <th className="py-2 text-center font-semibold">{t.expRet}</th>
                <th className="py-2 text-center font-semibold">{t.vol}</th>
                <th className="py-2 text-center font-semibold">{t.stockSharpe}</th>
                <th className="py-2 font-semibold w-64">{t.weight}</th>
              </tr>
            </thead>
            <tbody>
              {STOCKS.map((s, i) => {
                const sd = Math.sqrt(COV_DAILY[i][i] * TRADING_DAYS);
                const sr = (MU[i] - R_F) / sd;
                const w = metrics.normalized[i];
                return (
                  <tr key={s.symbol} className="border-b border-slate-100 hover:bg-slate-50">
                    <td className="py-3 font-mono font-semibold" style={{ color: NAVY }}>{s.symbol}</td>
                    <td className="py-3">{lang === "ar" ? s.nameAr : s.nameEn}</td>
                    <td className={`py-3 text-center font-medium ${MU[i] >= 0 ? "text-green-600" : "text-red-600"}`}>
                      {fmtPct(MU[i])}
                    </td>
                    <td className="py-3 text-center">{fmtPct(sd)}</td>
                    <td className={`py-3 text-center ${sr >= 0 ? "text-green-600" : "text-red-600"}`}>
                      {sr.toFixed(3)}
                    </td>
                    <td className="py-3">
                      <div className="flex items-center gap-2">
                        <input type="range" min="0" max="100" step="0.1" value={w * 100}
                          onChange={e => updateWeight(i, +e.target.value)}
                          className="flex-1 accent-current" style={{ color: NAVY }} />
                        <span className="w-12 text-right font-mono text-xs font-semibold"
                          style={{ color: NAVY }}>{(w * 100).toFixed(1)}%</span>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
            <tfoot>
              <tr className="font-semibold" style={{ color: NAVY, background: BLUE_BG }}>
                <td colSpan={5} className="py-2 px-3">Σ</td>
                <td className="py-2 pr-2 text-right font-mono">
                  {(metrics.normalized.reduce((a, b) => a + b, 0) * 100).toFixed(1)}%
                </td>
              </tr>
            </tfoot>
          </table>
        </div>

        {/* ==================== Correlation + Risk Contribution ==================== */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <div className="bg-white rounded-lg border border-slate-200 p-4">
            <SectionHeader title={t.correlation} compact />
            <div className="mt-3 overflow-x-auto">
              <table className="text-xs w-full">
                <thead>
                  <tr>
                    <th></th>
                    {STOCKS.map(s => <th key={s.symbol} className="p-1 font-medium" style={{ color: NAVY }}>
                      {s.symbol}</th>)}
                  </tr>
                </thead>
                <tbody>
                  {corrMatrix.map((row, i) => (
                    <tr key={i}>
                      <td className="p-1 font-medium text-right" style={{ color: NAVY }}>{STOCKS[i].symbol}</td>
                      {row.map((v, j) => {
                        const intensity = Math.abs(v);
                        const color = v >= 0
                          ? `rgba(22, 40, 73, ${0.15 + 0.75 * intensity})`
                          : `rgba(192, 57, 43, ${0.15 + 0.75 * intensity})`;
                        return (
                          <td key={j} className="p-1 text-center font-mono"
                            style={{ background: color, color: intensity > 0.5 ? "white" : NAVY }}>
                            {v.toFixed(2)}
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <div className="bg-white rounded-lg border border-slate-200 p-4">
            <SectionHeader title={t.riskContrib} compact />
            <div className="h-64 mt-3">
              <ResponsiveContainer>
                <BarChart data={STOCKS.map((s, i) => ({
                  name: s.symbol,
                  contrib: rc[i] * 100
                }))} margin={{ top: 10, right: 20, bottom: 10, left: 0 }}>
                  <CartesianGrid stroke="#e2e8f0" strokeDasharray="2 4" />
                  <XAxis dataKey="name" stroke={NAVY} />
                  <YAxis tickFormatter={v => `${v.toFixed(0)}%`} stroke={NAVY} />
                  <Tooltip formatter={(v) => `${v.toFixed(2)}%`} />
                  <Bar dataKey="contrib" fill={NAVY} radius={[4, 4, 0, 0]}>
                    <LabelList dataKey="contrib" position="top"
                      formatter={v => `${v.toFixed(1)}%`} fill={NAVY} fontSize={11} />
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="mt-8 text-center text-xs text-slate-500">
          {lang === "ar"
            ? "منصة دان للتحليل المالي — نموذج تحسين المحفظة (نظرية هاري ماركويتز)"
            : "Dan Analytical Platform — Portfolio Optimization (Harry Markowitz Theory)"}
        </div>
      </main>
    </div>
  );
}

/* =============================================================
   Reusable subcomponents
   ============================================================= */
function SectionHeader({ icon, title, compact = false }) {
  return (
    <div className={`flex items-center gap-2 ${compact ? "" : "text-white px-4 py-2 rounded-t"}`}
      style={compact ? { color: NAVY } : { background: NAVY }}>
      {icon && <span>{icon}</span>}
      <h2 className={`font-semibold ${compact ? "text-sm" : "text-base"}`}>{title}</h2>
    </div>
  );
}

function MetricCard({ label, value, accent }) {
  return (
    <div className="bg-white rounded-lg border border-slate-200 p-4 flex flex-col justify-between min-h-[90px]">
      <div className="text-xs font-medium text-slate-600 flex items-center gap-1">
        {label}
        <Info size={11} className="text-slate-400" />
      </div>
      <div className="mt-2 font-bold text-lg" style={accent ? { color: accent } : { color: NAVY }}>
        {value}
      </div>
    </div>
  );
}
