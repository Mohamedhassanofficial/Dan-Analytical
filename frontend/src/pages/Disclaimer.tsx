import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Navigate, useNavigate } from "react-router-dom";
import { AuthAPI, type DisclaimerOut } from "@/api/auth";
import { ApiError } from "@/api/client";
import AuthShell from "@/components/AuthShell";
import { useAuth } from "@/contexts/AuthContext";
import { useLocale } from "@/contexts/LocaleContext";

export default function DisclaimerPage() {
  const { t } = useTranslation();
  const { user, refresh } = useAuth();
  const { locale } = useLocale();
  const nav = useNavigate();

  const [disclaimer, setDisclaimer] = useState<DisclaimerOut | null>(null);
  const [loading, setLoading] = useState(true);
  const [accepted, setAccepted] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    AuthAPI.activeDisclaimer()
      .then(setDisclaimer)
      .catch((e: unknown) => {
        setError(e instanceof ApiError ? e.detail : t("errors.network"));
      })
      .finally(() => setLoading(false));
  }, [t]);

  if (!user) return <Navigate to="/login" replace />;
  if (user.disclaimer_accepted_at) {
    return <Navigate to={user.has_active_subscription ? "/" : "/subscribe"} replace />;
  }

  async function onAccept() {
    if (!disclaimer) return;
    setSubmitting(true);
    setError(null);
    try {
      await AuthAPI.acceptDisclaimer(disclaimer.version);
      await refresh();
      nav("/subscribe", { replace: true });
    } catch (e) {
      setError(e instanceof ApiError ? e.detail : t("errors.network"));
    } finally {
      setSubmitting(false);
    }
  }

  const body = disclaimer ? (locale === "ar" ? disclaimer.body_ar : disclaimer.body_en) : "";

  return (
    <AuthShell>
      <h1 className="mb-4 text-2xl font-semibold text-navy">{t("auth.disclaimer_title")}</h1>

      {loading ? (
        <p className="text-muted">{t("common.loading")}</p>
      ) : error && !disclaimer ? (
        <div className="badge-red">{error}</div>
      ) : (
        <>
          <div className="mb-4 max-h-72 overflow-y-auto whitespace-pre-line rounded-md border border-border bg-surface p-4 text-sm leading-relaxed">
            {body}
          </div>

          <label className="mb-4 flex items-start gap-2 text-sm">
            <input
              type="checkbox"
              className="mt-1"
              checked={accepted}
              onChange={(e) => setAccepted(e.target.checked)}
            />
            <span>{t("auth.disclaimer_accept")}</span>
          </label>

          {error && <div className="badge-red mb-3">{error}</div>}

          <button
            onClick={onAccept}
            disabled={!accepted || submitting}
            className="btn-primary w-full"
          >
            {submitting ? t("common.loading") : t("auth.disclaimer_accept")}
          </button>
        </>
      )}
    </AuthShell>
  );
}
