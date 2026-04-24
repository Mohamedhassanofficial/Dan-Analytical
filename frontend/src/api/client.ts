/**
 * Typed fetch wrapper for the `/api/v1/...` namespace.
 *
 * Features:
 *   - Injects `Authorization: Bearer <access>` from tokens.ts
 *   - On 401, transparently refreshes using the refresh token and retries ONCE
 *   - Deduplicates concurrent refresh attempts so only one network call flies
 *   - Throws `ApiError` with {status, detail} — callers use try/catch + type guard
 *
 * In dev the Vite proxy forwards /api/v1/* to http://localhost:8000.
 */
import {
  clearTokens,
  getAccessToken,
  getRefreshToken,
  setTokens,
} from "@/lib/tokens";

const BASE_URL = import.meta.env.VITE_API_BASE_URL || "/api/v1";

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly detail: string,
    public readonly body?: unknown,
  ) {
    super(detail);
  }
}

interface ApiOptions extends Omit<RequestInit, "body"> {
  body?: unknown;
  /** Set true for endpoints that return a binary blob (PDF). */
  blob?: boolean;
  /** Skip the auth header even if a token is present. */
  anonymous?: boolean;
}

let refreshInFlight: Promise<boolean> | null = null;

async function refreshAccessToken(): Promise<boolean> {
  if (refreshInFlight) return refreshInFlight;
  const refresh = getRefreshToken();
  if (!refresh) return false;

  refreshInFlight = (async () => {
    try {
      const res = await fetch(`${BASE_URL}/auth/refresh`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${refresh}`,
        },
        body: JSON.stringify({ refresh_token: refresh }),
      });
      if (!res.ok) return false;
      const data = (await res.json()) as {
        access_token: string;
        refresh_token: string;
      };
      setTokens(data.access_token, data.refresh_token);
      return true;
    } catch {
      return false;
    } finally {
      refreshInFlight = null;
    }
  })();

  return refreshInFlight;
}

async function parseResponse<T>(res: Response, blob: boolean): Promise<T> {
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    let body: unknown;
    try {
      body = await res.json();
      if (body && typeof body === "object" && "detail" in body) {
        const d = (body as { detail: unknown }).detail;
        if (typeof d === "string") detail = d;
      }
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(res.status, detail, body);
  }
  if (res.status === 204) return undefined as T;
  if (blob) return (await res.blob()) as unknown as T;
  return (await res.json()) as T;
}

export async function api<T = unknown>(
  path: string,
  opts: ApiOptions = {},
): Promise<T> {
  const { body, blob = false, anonymous = false, headers, ...rest } = opts;

  const doFetch = async (): Promise<Response> => {
    const finalHeaders: Record<string, string> = {
      Accept: blob ? "application/pdf, application/octet-stream" : "application/json",
      ...(headers as Record<string, string> | undefined),
    };
    if (body !== undefined && !(body instanceof FormData)) {
      finalHeaders["Content-Type"] = "application/json";
    }
    if (!anonymous) {
      const token = getAccessToken();
      if (token) finalHeaders["Authorization"] = `Bearer ${token}`;
    }

    const init: RequestInit = { ...rest, headers: finalHeaders };
    if (body !== undefined) {
      init.body = body instanceof FormData ? body : JSON.stringify(body);
    }
    return fetch(`${BASE_URL}${path}`, init);
  };

  let res = await doFetch();

  if (res.status === 401 && !anonymous) {
    const refreshed = await refreshAccessToken();
    if (refreshed) {
      res = await doFetch();
    } else {
      clearTokens();
    }
  }
  return parseResponse<T>(res, blob);
}

export const apiUrl = (path: string): string => `${BASE_URL}${path}`;
