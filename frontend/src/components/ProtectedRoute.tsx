import { Navigate, Outlet, useLocation } from "react-router-dom";
import { useAuth } from "@/contexts/AuthContext";

/**
 * Gate for any authenticated route. Optionally enforce:
 *   - admin=true  → route requires is_admin
 *   - requireDisclaimer=true → user must have accepted the disclaimer
 *   - requireSubscription=true → user must have an active subscription
 */
interface Props {
  admin?: boolean;
  requireDisclaimer?: boolean;
  requireSubscription?: boolean;
}

export default function ProtectedRoute({
  admin = false,
  requireDisclaimer = false,
  requireSubscription = false,
}: Props) {
  const { user, loading } = useAuth();
  const loc = useLocation();

  if (loading) {
    return (
      <div className="flex h-screen items-center justify-center text-muted">
        ...
      </div>
    );
  }
  if (!user) {
    return <Navigate to="/login" replace state={{ from: loc }} />;
  }
  if (admin && !user.is_admin) {
    return <Navigate to="/" replace />;
  }
  if (requireDisclaimer && !user.disclaimer_accepted_at) {
    return <Navigate to="/disclaimer" replace />;
  }
  if (requireSubscription && !user.has_active_subscription) {
    return <Navigate to="/subscribe" replace />;
  }
  return <Outlet />;
}
