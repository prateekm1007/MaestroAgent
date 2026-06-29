// lib/auth-context.tsx — React context for authentication state.

'use client';

import { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import { auth as authApi } from './api';
import type { AuthUser } from '@/types';

interface AuthContextValue {
  user: AuthUser | null;
  loading: boolean;
  login: (email: string, password: string, orgSlug?: string) => Promise<void>;
  register: (data: { email: string; password: string; name: string; org_name: string; org_slug: string; industry?: string }) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null;
    if (!token) {
      setLoading(false);
      return;
    }
    authApi.me()
      .then(({ user }) => setUser(user))
      .catch(() => {
        localStorage.removeItem('access_token');
        setUser(null);
      })
      .finally(() => setLoading(false));
  }, []);

  const login = async (email: string, password: string, orgSlug?: string) => {
    const { user, tokens } = await authApi.login({ email, password, org_slug: orgSlug });
    localStorage.setItem('access_token', tokens.access_token);
    setUser(user);
  };

  const register = async (data: { email: string; password: string; name: string; org_name: string; org_slug: string; industry?: string }) => {
    const { user, tokens } = await authApi.register(data);
    localStorage.setItem('access_token', tokens.access_token);
    setUser(user);
  };

  const logout = async () => {
    try { await authApi.logout(); } catch {}
    localStorage.removeItem('access_token');
    setUser(null);
  };

  return (
    <AuthContext.Provider value={{ user, loading, login, register, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}
