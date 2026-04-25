import { Navigate, Route, Routes } from "react-router-dom";
import Layout from "@/components/Layout";
import ProtectedRoute from "@/components/ProtectedRoute";

import LoginPage from "@/pages/Login";
import RegisterPage from "@/pages/Register";
import DisclaimerPage from "@/pages/Disclaimer";
import SubscribePage from "@/pages/Subscribe";
import PaymentReturnPage from "@/pages/PaymentReturn";

import DashboardPage from "@/pages/Dashboard";
import ScreenerPage from "@/pages/Screener";
import OptimizePage from "@/pages/Optimize";
import HistoryPage from "@/pages/History";
import PortfolioListPage from "@/pages/PortfolioList";
import PortfolioDetailsPage from "@/pages/PortfolioDetails";
import AdminConfigPage from "@/pages/admin/Config";
import AdminUploadPage from "@/pages/admin/Upload";

export default function App() {
  return (
    <Routes>
      {/* Public routes */}
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />
      <Route path="/payment-return" element={<PaymentReturnPage />} />

      {/* Authenticated (no disclaimer / subscription yet) */}
      <Route element={<ProtectedRoute />}>
        <Route path="/disclaimer" element={<DisclaimerPage />} />
        <Route path="/subscribe" element={<SubscribePage />} />
      </Route>

      {/* Fully-gated app (disclaimer + subscription + layout shell) */}
      <Route
        element={
          <ProtectedRoute requireDisclaimer requireSubscription />
        }
      >
        <Route element={<Layout />}>
          <Route path="/" element={<DashboardPage />} />
          <Route path="/screener" element={<ScreenerPage />} />
          <Route path="/optimize" element={<OptimizePage />} />
          <Route path="/portfolios" element={<PortfolioListPage />} />
          <Route path="/portfolios/:id" element={<PortfolioDetailsPage />} />
          <Route path="/history" element={<HistoryPage />} />
        </Route>
      </Route>

      {/* Admin (inherits disclaimer + subscription from above; add is_admin) */}
      <Route
        element={<ProtectedRoute admin requireDisclaimer requireSubscription />}
      >
        <Route element={<Layout />}>
          <Route path="/admin/config" element={<AdminConfigPage />} />
          <Route path="/admin/upload" element={<AdminUploadPage />} />
        </Route>
      </Route>

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
