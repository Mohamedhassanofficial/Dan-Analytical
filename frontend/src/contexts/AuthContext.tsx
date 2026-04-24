import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { AuthAPI, type RegisterPayload, type User } from "@/api/auth";
import { clearTokens, getAccessToken, setTokens } from "@/lib/tokens";

interface AuthContextValue {
  user: User | null;
  loading: boolean;
  login: (identifier: string, password: string) => Promise<void>;
  register: (p: RegisterPayload) => Promise<void>;
  logout: () => void;
  refresh: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    if (!getAccessToken()) {
      setUser(null);
      return;
    }
    try {
      const me = await AuthAPI.me();
      setUser(me);
    } catch {
      setUser(null);
      clearTokens();
    }
  }, []);

  // Hydrate on mount
  useEffect(() => {
    (async () => {
      await refresh();
      setLoading(false);
    })();
  }, [refresh]);

  const login = useCallback(async (identifier: string, password: string) => {
    const pair = await AuthAPI.login(identifier, password);
    setTokens(pair.access_token, pair.refresh_token);
    const me = await AuthAPI.me();
    setUser(me);
  }, []);

  const register = useCallback(async (p: RegisterPayload) => {
    await AuthAPI.register(p);
    // Per PDF flow: auto-login after registration so the user can accept
    // the disclaimer and proceed to payment without a second password entry.
    await login(p.email, p.password);
  }, [login]);

  const logout = useCallback(() => {
    clearTokens();
    setUser(null);
  }, []);

  const value = useMemo(
    () => ({ user, loading, login, register, logout, refresh }),
    [user, loading, login, register, logout, refresh],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be inside <AuthProvider>");
  return ctx;
}
