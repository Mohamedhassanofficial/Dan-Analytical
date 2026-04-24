import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import AuthShell from "@/components/AuthShell";
import { useAuth } from "@/contexts/AuthContext";

/**
 * Landing page after the gateway redirects the user back. Poll /auth/me for up
 * to ~20s waiting for the webhook to flip has_active_subscription → true.
 */
export default function PaymentReturnPage() {
  const { t } = useTranslation();
  const { refresh, user } = useAuth();
  const nav = useNavigate();
  const [tries, setTries] = useState(0);

  useEffect(() => {
    let mounted = true;
    let id: ReturnType<typeof setTimeout> | null = null;

    async function poll() {
      await refresh();
      if (!mounted) return;
      if (user?.has_active_subscription) {
        nav("/", { replace: true });
        return;
      }
      if (tries >= 10) {
        nav("/subscribe", { replace: true });
        return;
      }
      setTries((n) => n + 1);
      id = setTimeout(poll, 2000);
    }
    void poll();
    return () => {
      mounted = false;
      if (id) clearTimeout(id);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <AuthShell>
      <h1 className="mb-2 text-xl font-semibold text-navy">
        {t("subscribe.redirecting")}
      </h1>
      <p className="text-sm text-muted">{t("common.loading")}</p>
    </AuthShell>
  );
}
