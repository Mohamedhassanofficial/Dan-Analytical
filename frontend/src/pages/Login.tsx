import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { Link, Navigate, useLocation, useNavigate } from "react-router-dom";
import AuthShell from "@/components/AuthShell";
import { ApiError } from "@/api/client";
import { useAuth } from "@/contexts/AuthContext";

interface LocationState { from?: { pathname?: string } }

export default function LoginPage() {
  const { t } = useTranslation();
  const { user, login } = useAuth();
  const nav = useNavigate();
  const loc = useLocation();
  const [identifier, setIdentifier] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  if (user) {
    const from = (loc.state as LocationState | null)?.from?.pathname ?? "/";
    return <Navigate to={from} replace />;
  }

  async function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await login(identifier, password);
      nav("/", { replace: true });
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        setError(t("errors.auth_invalid"));
      } else if (err instanceof ApiError) {
        setError(err.detail);
      } else {
        setError(t("errors.network"));
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <AuthShell>
      <h1 className="mb-1 text-2xl font-semibold text-navy">{t("auth.login_title")}</h1>
      <p className="mb-6 text-sm text-muted">{t("app.tagline")}</p>

      <form className="flex flex-col gap-4" onSubmit={onSubmit}>
        <div>
          <label className="label" htmlFor="identifier">{t("auth.login_identifier")}</label>
          <input
            id="identifier"
            className="input"
            autoComplete="username"
            required
            value={identifier}
            onChange={(e) => setIdentifier(e.target.value)}
          />
        </div>

        <div>
          <label className="label" htmlFor="password">{t("auth.login_password")}</label>
          <input
            id="password"
            className="input"
            type="password"
            autoComplete="current-password"
            required
            minLength={10}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </div>

        {error && <div className="badge-red">{error}</div>}

        <button type="submit" className="btn-primary" disabled={submitting}>
          {submitting ? t("auth.logging_in") : t("auth.login_submit")}
        </button>
      </form>

      <p className="mt-6 text-center text-sm text-muted">
        {t("auth.login_no_account")}{" "}
        <Link to="/register" className="font-medium text-brand-600 hover:underline">
          {t("auth.register_link")}
        </Link>
      </p>
    </AuthShell>
  );
}
