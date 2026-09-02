import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { apiClient } from "../api/client";

interface CurrentUser {
  user_id: string;
  company_id: string;
  role: "dispatcher" | "manager";
}

interface AuthContextValue {
  user: CurrentUser | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const token = localStorage.getItem("access_token");
    if (!token) {
      setLoading(false);
      return;
    }
    apiClient
      .get<CurrentUser>("/api/auth/me")
      .then((res) => setUser(res.data))
      .catch(() => {
        localStorage.removeItem("access_token");
        localStorage.removeItem("refresh_token");
      })
      .finally(() => setLoading(false));
  }, []);

  async function login(email: string, password: string) {
    const { data } = await apiClient.post("/api/auth/login", { email, password });
    localStorage.setItem("access_token", data.access_token);
    localStorage.setItem("refresh_token", data.refresh_token);
    const me = await apiClient.get<CurrentUser>("/api/auth/me");
    setUser(me.data);
  }

  async function logout() {
    const refreshToken = localStorage.getItem("refresh_token");
    try {
      if (refreshToken) await apiClient.post("/api/auth/logout", { refresh_token: refreshToken });
    } catch {
      // đăng xuất phía client vẫn tiếp tục dù call logout lỗi (vd token đã hết hạn)
    }
    localStorage.removeItem("access_token");
    localStorage.removeItem("refresh_token");
    setUser(null);
  }

  return <AuthContext.Provider value={{ user, loading, login, logout }}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth phải dùng trong AuthProvider");
  return ctx;
}
