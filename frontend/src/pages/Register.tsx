import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { Link, Navigate, useNavigate } from "react-router-dom";
import AuthShell from "@/components/AuthShell";
import { ApiError } from "@/api/client";
import { useAuth } from "@/contexts/AuthContext";
import { useLocale } from "@/contexts/LocaleContext";

export default function RegisterPage() {
  const { t } = useTranslation();
  const { user, register } = useAuth();
  const { locale } = useLocale();
  const nav = useNavigate();

  const [form, setForm] = useState({
    national_id: "",
    mobile: "",
    email: "",
    password: "",
    full_name_ar: "",
    full_name_en: "",
  });
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  if (user) return <Navigate to="/disclaimer" replace />;

  function field<K extends keyof typeof form>(k: K, value: string) {
    setForm({ ...form, [k]: value });
  }

  async function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await register({
        national_id: form.national_id,
        mobile: form.mobile,
        email: form.email,
        password: form.password,
        full_name_ar: form.full_name_ar || undefined,
        full_name_en: form.full_name_en || undefined,
        preferred_locale: locale,
      });
      nav("/disclaimer", { replace: true });
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.status === 409 ? t("errors.auth_exists") : err.detail);
      } else {
        setError(t("errors.network"));
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <AuthShell>
      <h1 className="mb-1 text-2xl font-semibold text-navy">{t("auth.register_title")}</h1>
      <p className="mb-6 text-sm text-muted">{t("app.tagline")}</p>

      <form className="flex flex-col gap-3" onSubmit={onSubmit}>
        <div>
          <label className="label" htmlFor="national_id">{t("auth.register_national_id")}</label>
          <input
            id="national_id"
            className="input"
            required
            pattern="\d{10}"
            maxLength={10}
            value={form.national_id}
            onChange={(e) => field("national_id", e.target.value)}
          />
        </div>
        <div>
          <label className="label" htmlFor="mobile">{t("auth.register_mobile")}</label>
          <input
            id="mobile"
            className="input"
            required
            autoComplete="tel"
            placeholder="+9665XXXXXXXX"
            value={form.mobile}
            onChange={(e) => field("mobile", e.target.value)}
          />
        </div>
        <div>
          <label className="label" htmlFor="email">{t("auth.register_email")}</label>
          <input
            id="email"
            className="input"
            type="email"
            autoComplete="email"
            required
            value={form.email}
            onChange={(e) => field("email", e.target.value)}
          />
        </div>
        <div>
          <label className="label" htmlFor="password">{t("auth.register_password")}</label>
          <input
            id="password"
            className="input"
            type="password"
            minLength={10}
            required
            autoComplete="new-password"
            value={form.password}
            onChange={(e) => field("password", e.target.value)}
          />
        </div>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <div>
            <label className="label" htmlFor="name_ar">{t("auth.register_full_name_ar")}</label>
            <input
              id="name_ar"
              className="input"
              dir="rtl"
              value={form.full_name_ar}
              onChange={(e) => field("full_name_ar", e.target.value)}
            />
          </div>
          <div>
            <label className="label" htmlFor="name_en">{t("auth.register_full_name_en")}</label>
            <input
              id="name_en"
              className="input"
              dir="ltr"
              value={form.full_name_en}
              onChange={(e) => field("full_name_en", e.target.value)}
            />
          </div>
        </div>

        {error && <div className="badge-red">{error}</div>}

        <button type="submit" className="btn-primary mt-2" disabled={submitting}>
          {submitting ? t("auth.registering") : t("auth.register_submit")}
        </button>
      </form>

      <p className="mt-6 text-center text-sm text-muted">
        {t("auth.register_have_account")}{" "}
        <Link to="/login" className="font-medium text-brand-600 hover:underline">
          {t("auth.login_link")}
        </Link>
      </p>
    </AuthShell>
  );
}
