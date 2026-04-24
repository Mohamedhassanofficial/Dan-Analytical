import { api } from "./client";

export interface TokenPair {
  access_token: string;
  refresh_token: string;
  token_type: "bearer";
  access_expires_in_sec: number;
  refresh_expires_in_sec: number;
}

export interface User {
  id: number;
  national_id: string;
  mobile: string;
  email: string;
  full_name_ar: string | null;
  full_name_en: string | null;
  preferred_locale: string;
  is_active: boolean;
  is_admin: boolean;
  disclaimer_accepted_at: string | null;
  last_login_at: string | null;
  has_active_subscription: boolean;
}

export interface DisclaimerOut {
  version: string;
  body_ar: string;
  body_en: string;
}

export interface RegisterPayload {
  national_id: string;
  mobile: string;
  email: string;
  password: string;
  full_name_ar?: string;
  full_name_en?: string;
  preferred_locale?: "ar" | "en";
}

export const AuthAPI = {
  register: (p: RegisterPayload) =>
    api<User>("/auth/register", { method: "POST", body: p, anonymous: true }),

  login: (identifier: string, password: string) =>
    api<TokenPair>("/auth/login", {
      method: "POST",
      body: { identifier, password },
      anonymous: true,
    }),

  me: () => api<User>("/auth/me"),

  activeDisclaimer: () => api<DisclaimerOut>("/auth/disclaimer/active", { anonymous: true }),

  acceptDisclaimer: (version: string) =>
    api<void>("/auth/disclaimer/accept", {
      method: "POST",
      body: { disclaimer_version: version },
    }),
};
