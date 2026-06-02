import React, { createContext, useContext, useEffect, useState, useCallback } from "react";
import api, { setAccessToken, getAccessToken } from "../lib/api";

const Ctx = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  const fetchMe = useCallback(async () => {
    try {
      const r = await api.get("/auth/me");
      setUser(r.data);
    } catch (_) {
      setUser(null);
    }
  }, []);

  useEffect(() => {
    (async () => {
      // Try to refresh from cookie on app load
      try {
        const r = await api.post("/auth/refresh", {});
        if (r.data?.access_token) {
          setAccessToken(r.data.access_token);
          await fetchMe();
        }
      } catch (_) { /* not logged in */ }
      setLoading(false);
    })();
  }, [fetchMe]);

  const login = async (email, password) => {
    const r = await api.post("/auth/login", { email, password });
    setAccessToken(r.data.access_token);
    setUser(r.data.user);
    return r.data.user;
  };
  const register = async (payload) => {
    const r = await api.post("/auth/register", payload);
    setAccessToken(r.data.access_token);
    setUser(r.data.user);
    return r.data.user;
  };
  const logout = async () => {
    try { await api.post("/auth/logout", {}); } catch (_) {}
    setAccessToken(null);
    setUser(null);
  };

  return (
    <Ctx.Provider value={{ user, loading, login, register, logout, refreshMe: fetchMe }}>
      {children}
    </Ctx.Provider>
  );
}

export const useAuth = () => useContext(Ctx);
