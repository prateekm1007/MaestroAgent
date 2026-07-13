/**
 * Shared React contexts for the Maestro Personal mobile app.
 *
 * Three providers live here:
 *  - ThemeProvider  — light/dark mode toggle (light is the default)
 *  - AuthProvider   — bearer token + LLM status, persisted via AsyncStorage
 *  - ConsentProvider — recording consent flag for the Live Copilot
 *
 * The screens import { useTheme, useAuth, useConsent } from here. App.tsx
 * imports the providers and wraps the navigation tree with them.
 */

import React, { createContext, useContext, useEffect, useState } from 'react';
import AsyncStorage from '@react-native-async-storage/async-storage';

import * as api from './api/client';
import { ThemeMode } from './theme/colors';

// ═══════════════════════════════════════════════════════════════════
// THEME CONTEXT
// ═══════════════════════════════════════════════════════════════════

const ThemeCtx = createContext({ mode: 'dark' as ThemeMode, toggle: () => {} });
export const useTheme = () => useContext(ThemeCtx);

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [mode, setMode] = useState<ThemeMode>('light');
  const toggle = () => setMode(m => m === 'dark' ? 'light' : 'dark');
  return <ThemeCtx.Provider value={{ mode, toggle }}>{children}</ThemeCtx.Provider>;
}

// ═══════════════════════════════════════════════════════════════════
// AUTH CONTEXT
// ═══════════════════════════════════════════════════════════════════

const AuthCtx = createContext<{
  token: string | null;
  login: (password: string) => Promise<boolean>;
  logout: () => void;
  llmStatus: api.LLMStatus | null;
}>({ token: null, login: async () => false, logout: () => {}, llmStatus: null });

export const useAuth = () => useContext(AuthCtx);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [token, setToken] = useState<string | null>(null);
  const [llmStatus, setLLMStatus] = useState<api.LLMStatus | null>(null);

  useEffect(() => {
    AsyncStorage.getItem('maestro_token').then(t => { if (t) setToken(t); });
  }, []);

  useEffect(() => {
    if (token) {
      api.getLLMStatus().then(setLLMStatus).catch(() => {});
    }
  }, [token]);

  const login = async (password: string): Promise<boolean> => {
    try {
      const result = await api.login(password);
      await AsyncStorage.setItem('maestro_token', result.token);
      setToken(result.token);
      return true;
    } catch (e) {
      return false;
    }
  };

  const logout = () => {
    AsyncStorage.removeItem('maestro_token');
    setToken(null);
  };

  return <AuthCtx.Provider value={{ token, login, logout, llmStatus }}>{children}</AuthCtx.Provider>;
}

// ═══════════════════════════════════════════════════════════════════
// CONSENT CONTEXT (Live Copilot recording consent)
// ═══════════════════════════════════════════════════════════════════

const ConsentContext = createContext<{ hasConsent: boolean; grant: () => void; revoke: () => void }>({
  hasConsent: false, grant: () => {}, revoke: () => {},
});
export const useConsent = () => useContext(ConsentContext);

export function ConsentProvider({ children }: { children: React.ReactNode }) {
  const [hasConsent, setHasConsent] = useState(false);
  useEffect(() => {
    AsyncStorage.getItem('maestro_consent').then(v => { if (v === 'true') setHasConsent(true); });
  }, []);
  const grant = () => { setHasConsent(true); AsyncStorage.setItem('maestro_consent', 'true'); };
  const revoke = () => { setHasConsent(false); AsyncStorage.removeItem('maestro_consent'); };
  return <ConsentContext.Provider value={{ hasConsent, grant, revoke }}>{children}</ConsentContext.Provider>;
}
