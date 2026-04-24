import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Navigate } from "react-router-dom";
import { CreditCard } from "lucide-react";
import { PaymentsAPI, type SubscriptionOut } from "@/api/payments";
import { ApiError } from "@/api/client";
import AuthShell from "@/components/AuthShell";
import { useAuth } from "@/contexts/AuthContext";
import { useLocale } from "@/contexts/LocaleContext";

const PRICE = 199;
const GATEWAY_LABELS: Record<string, string> = {
  stcpay: "STC Pay",
  paytabs: "PayTabs",
};

export default function SubscribePage() {
  const { t } = useTranslation();
  const { user, refresh } = useAuth();
  const { locale } = useLocale();

  const [subs, setSubs] = useState<SubscriptionOut[]>([]);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    PaymentsAPI.subscriptions()
      .then(setSubs)
      .catch(() => setSubs([]))
      .finally(() => setLoading(false));
  }, []);

  if (!user) return <Navigate to="/login" replace />;
  if (!user.disclaimer_accepted_at) return <Navigate to="/disclaimer" replace />;
  if (user.has_active_subscription) return <Navigate to="/" replace />;

  async function onSubscribe() {
    setSubmitting(true);
    setError(null);
    try {
      const checkout = await PaymentsAPI.subscribe(`${window.location.origin}/payment-return`);
      // In test mode the redirect_url returns us directly; in prod it sends the
      // user to the gateway's hosted payment page.
      window.location.href = checkout.redirect_url;
    } catch (e) {
      setError(e instanceof ApiError ? e.detail : t("errors.network"));
      setSubmitting(false);
    }
  }

  // Detect which gateway the admin has activated by inspecting any pending row,
  // falling back to STC Pay for the label.
  const gatewayName = subs[0]?.gateway ?? "stcpay";
  const gatewayLabel = GATEWAY_LABELS[gatewayName] ?? gatewayName;

  const fmt = new Intl.DateTimeFormat(locale === "ar" ? "ar-SA" : "en-GB", {
    dateStyle: "medium",
  });

  return (
    <AuthShell>
      <div className="mb-5 flex items-center gap-3">
        <div className="grid h-10 w-10 place-items-center rounded-lg bg-brand-100 text-brand-700">
          <CreditCard size={20} />
        </div>
        <div>
          <h1 className="text-xl font-semibold text-navy">{t("subscribe.title")}</h1>
          <p className="text-sm text-muted">{t("app.tagline")}</p>
        </div>
      </div>

      <div className="mb-5 rounded-lg bg-surface p-4">
        <p className="text-2xl font-semibold text-navy">
          {t("subscribe.price_monthly", { amount: PRICE })}
        </p>
        <p className="mt-2 text-sm text-muted">{t("subscribe.benefits")}</p>
      </div>

      {error && <div className="badge-red mb-3">{error}</div>}

      <button
        onClick={onSubscribe}
        disabled={submitting}
        className="btn-primary w-full"
      >
        {submitting
          ? t("subscribe.redirecting")
          : t("subscribe.proceed", { gateway: gatewayLabel })}
      </button>

      {!loading && subs.length > 0 && (
        <div className="mt-8">
          <h2 className="mb-2 text-sm font-semibold text-ink">{t("subscribe.history_title")}</h2>
          <ul className="divide-y divide-border rounded-lg border border-border text-sm">
            {subs.map((s) => (
              <li key={s.id} className="flex items-center justify-between px-3 py-2">
                <div>
                  <div className="font-medium">
                    {s.amount} {s.currency} — {GATEWAY_LABELS[s.gateway] ?? s.gateway}
                  </div>
                  {s.expires_at && (
                    <div className="text-xs text-muted">
                      {t("subscribe.active_until", { date: fmt.format(new Date(s.expires_at)) })}
                    </div>
                  )}
                </div>
                <span className={statusBadge(s.status)}>{t(`subscribe.status_${s.status}`)}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="mt-6 text-center">
        <button onClick={() => void refresh()} className="btn-ghost text-xs">
          {t("common.retry")}
        </button>
      </div>
    </AuthShell>
  );
}

function statusBadge(s: SubscriptionOut["status"]): string {
  switch (s) {
    case "completed": return "badge-ok";
    case "failed":    return "badge-error";
    case "refunded":  return "badge-warn";
    default:          return "badge-info";
  }
}
