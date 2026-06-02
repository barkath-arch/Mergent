import React, { createContext, useContext, useEffect, useState, useCallback } from 'react';
import api, { setAccessToken, restoreToken } from './api';

interface User {
  id: string;
  name: string;
  email: string;
  role: string;
  [key: string]: any;
}

interface AuthContextType {
  user: User | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<User>;
  register: (payload: any) => Promise<User>;
  logout: () => Promise<void>;
  refreshMe: () => Promise<void>;
}

const Ctx = createContext<AuthContextType | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchMe = useCallback(async () => {
    try {
      const r = await api.get('/auth/me');
      setUser(r.data);
    } catch {
      setUser(null);
    }
  }, []);

  useEffect(() => {
    (async () => {
      try {
        await restoreToken();
        const r = await api.post('/auth/refresh', {});
        if (r.data?.access_token) {
          setAccessToken(r.data.access_token);
          await fetchMe();
        }
      } catch { /* not logged in */ }
      setLoading(false);
    })();
  }, [fetchMe]);

  const login = async (email: string, password: string) => {
    const r = await api.post('/auth/login', { email, password });
    setAccessToken(r.data.access_token);
    setUser(r.data.user);
    return r.data.user;
  };

  const register = async (payload: any) => {
    const r = await api.post('/auth/register', payload);
    setAccessToken(r.data.access_token);
    setUser(r.data.user);
    return r.data.user;
  };

  const logout = async () => {
    try { await api.post('/auth/logout', {}); } catch {}
    setAccessToken(null);
    setUser(null);
  };

  return (
    <Ctx.Provider value={{ user, loading, login, register, logout, refreshMe: fetchMe }}>
      {children}
    </Ctx.Provider>
  );
}

export const useAuth = () => {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error('useAuth must be inside AuthProvider');
  return ctx;
};
