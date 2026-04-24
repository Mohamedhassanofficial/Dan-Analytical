/**
 * Access/refresh token persistence.
 *
 * localStorage is the simplest venue but exposes tokens to XSS. For Phase D
 * we move to HttpOnly+Secure cookies issued by the backend to reduce the
 * PDPL attack surface. Until then, use this module as the only place tokens
 * are read/written so the migration is mechanical.
 */

const ACCESS_KEY = "tadawul.access_token";
const REFRESH_KEY = "tadawul.refresh_token";

export function getAccessToken(): string | null {
  return localStorage.getItem(ACCESS_KEY);
}
export function getRefreshToken(): string | null {
  return localStorage.getItem(REFRESH_KEY);
}
export function setTokens(access: string, refresh: string): void {
  localStorage.setItem(ACCESS_KEY, access);
  localStorage.setItem(REFRESH_KEY, refresh);
}
export function clearTokens(): void {
  localStorage.removeItem(ACCESS_KEY);
  localStorage.removeItem(REFRESH_KEY);
}
