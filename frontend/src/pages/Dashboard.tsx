import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
  Legend,
} from "recharts";
import { PortfolioAPI, type PortfolioRun } from "@/api/portfolio";
import { useAuth } from "@/contexts/AuthContext";
import { colorFor, fmtNum, fmtPct } from "@/lib/format";

export default function DashboardPage() {
  const { t } = useTranslation();
  const { user } = useAuth();
  const nav = useNavigate();
  const [runs, setRuns] = useState<PortfolioRun[] | null>(null);

  useEffect(() => {
    PortfolioAPI.runs(20).then(setRuns).catch(() => setRuns([]));
  }, []);

  const latest = runs?.find((r) => r.success && r.weights);

  const weightData = useMemo(() => {
    if (!latest?.weights) return [];
    return Object.entries(latest.weights)
      .filter(([, v]) => v >= 1e-4)
      .map(([ticker, weight]) => ({ ticker, weight }))
      .sort((a, b) => b.weight - a.weight);
  }, [latest]);

  const name =
    (user?.full_name_ar || user?.full_name_en || user?.email || "").split("@")[0];

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold text-navy">{t("dashboard.title")}</h1>
        <p className="mt-1 text-sm text-muted">
          {t("dashboard.welcome", { name })}
        </p>
      </div>

      {!runs ? (
        <p className="text-muted">{t("common.loading")}</p>
      ) : !latest ? (
        <div className="card text-center">
          <p className="mb-4 text-muted">{t("dashboard.run_to_see")}</p>
          <button onClick={() => nav("/optimize")} className="btn-primary">
            {t("nav.optimize")}
          </button>
        </div>
      ) : (
        <>
          {/* Metrics grid */}
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <Stat label={t("dashboard.sharpe")} value={fmtNum(latest.sharpe ?? 0, 4)} />
            <Stat
              label={t("dashboard.expected_return")}
              value={fmtPct(latest.expected_return ?? 0)}
            />
            <Stat
              label={t("dashboard.volatility")}
              value={fmtPct(latest.volatility ?? 0)}
            />
            <Stat
              label={t("dashboard.var_95_daily")}
              value={latest.var_95 != null ? fmtPct(latest.var_95) : t("common.not_available")}
            />
          </div>

          <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
            {/* Allocation pie */}
            <div className="card">
              <h2 className="mb-3 text-lg font-semibold">{t("dashboard.allocation_title")}</h2>
              <ResponsiveContainer width="100%" height={260}>
                <PieChart>
                  <Pie
                    data={weightData}
                    dataKey="weight"
                    nameKey="ticker"
                    innerRadius={60}
                    outerRadius={100}
                    paddingAngle={1}
                  >
                    {weightData.map((_, i) => (
                      <Cell key={i} fill={colorFor(i)} />
                    ))}
                  </Pie>
                  <Tooltip formatter={(v: number) => fmtPct(v)} />
                  <Legend />
                </PieChart>
              </ResponsiveContainer>
            </div>

            {/* Weight bar (as a proxy for risk contribution without /metrics call) */}
            <div className="card">
              <h2 className="mb-3 text-lg font-semibold">
                {t("optimize.weights_header")}
              </h2>
              <ResponsiveContainer width="100%" height={260}>
                <BarChart data={weightData} layout="vertical" margin={{ left: 10 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#eef2f6" />
                  <XAxis
                    type="number"
                    tickFormatter={(v) => `${(v * 100).toFixed(0)}%`}
                  />
                  <YAxis dataKey="ticker" type="category" width={70} />
                  <Tooltip formatter={(v: number) => fmtPct(v)} />
                  <Bar dataKey="weight" fill="#305d9a" />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* A tiny frontier preview (static scatter of latest runs) */}
          {runs && runs.length > 1 && (
            <div className="card">
              <h2 className="mb-3 text-lg font-semibold">{t("dashboard.frontier_title")}</h2>
              <ResponsiveContainer width="100%" height={280}>
                <ScatterChart>
                  <CartesianGrid strokeDasharray="3 3" stroke="#eef2f6" />
                  <XAxis
                    type="number"
                    dataKey="volatility"
                    name={t("dashboard.volatility")}
                    tickFormatter={(v) => `${(v * 100).toFixed(0)}%`}
                  />
                  <YAxis
                    type="number"
                    dataKey="expected_return"
                    name={t("dashboard.expected_return")}
                    tickFormatter={(v) => `${(v * 100).toFixed(0)}%`}
                  />
                  <Tooltip
                    formatter={(v: number) => fmtPct(v)}
                    labelFormatter={() => ""}
                  />
                  <Scatter
                    data={runs
                      .filter((r) => r.expected_return != null && r.volatility != null)
                      .map((r) => ({
                        volatility: Number(r.volatility),
                        expected_return: Number(r.expected_return),
                      }))}
                    fill="#162849"
                  />
                </ScatterChart>
              </ResponsiveContainer>
            </div>
          )}
        </>
      )}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="stat-card">
      <span className="stat-label">{label}</span>
      <span className="stat-value">{value}</span>
    </div>
  );
}
