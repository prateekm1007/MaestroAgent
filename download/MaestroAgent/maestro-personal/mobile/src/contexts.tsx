/**
 * Shared React contexts for the Maestro Personal mobile app.
 *
 * Three providers live here:
 *  - ThemeProvider  — light/dark mode toggle (light is the default)
 *  - AuthProvider   — bearer token (SecureStore) + LLM status
 *  - ConsentProvider — generic consent flag (currently unused; reserved
 *    for future voice-recording features). The screen that previously
 *    consumed this context was removed in the V2 4-tab redesign
 *    (P0-4 audit fix 2026-07-15).
 *
 * Phase 1 fix: AuthProvider uses SecureStore (not AsyncStorage) for token.
 * Phase 2: Added OnboardingContext for first-launch flow.
 */

import React, { createContext, useContext, useEffect, useState } from 'react';
import AsyncStorage from '@react-native-async-storage/async-storage';
import * as SecureStore from 'expo-secure-store';

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
// AUTH CONTEXT (Phase 1: SecureStore-only)
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
    // Phase 1: read token from SecureStore (native) or AsyncStorage (web)
    SecureStore.getItemAsync('maestro_token')
      .then(t => { if (t) setToken(t); })
      .catch(() => {
        // Web fallback: SecureStore not available
        AsyncStorage.getItem('maestro_token').then(t => { if (t) setToken(t); }).catch(() => {});
      });
  }, []);

  useEffect(() => {
    if (token) {
      api.getLLMStatus().then(setLLMStatus).catch(() => {});
    }
  }, [token]);

  const login = async (password: string): Promise<boolean> => {
    try {
      const result = await api.login(password);
      if (!result || !result.token) {
        return false;
      }
      // Store token — use SecureStore on native, AsyncStorage on web
      try {
        await SecureStore.setItemAsync('maestro_token', result.token);
      } catch {
        // Web fallback: SecureStore not available on web
        await AsyncStorage.setItem('maestro_token', result.token);
      }
      setToken(result.token);
      return true;
    } catch (e: any) {
      console.error('Login failed:', e?.message || e);
      return false;
    }
  };

  const logout = () => {
    // Phase 1: delete from SecureStore + best-effort server revoke
    try {
      fetch(`${api.getHost()}/api/auth/revoke`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` },
      });
    } catch { /* non-fatal */ }
    try {
      SecureStore.deleteItemAsync('maestro_token').catch(() => {});
    } catch {
      AsyncStorage.removeItem('maestro_token').catch(() => {});
    }
    setToken(null);
  };

  return <AuthCtx.Provider value={{ token, login, logout, llmStatus }}>{children}</AuthCtx.Provider>;
}

// ═══════════════════════════════════════════════════════════════════
// CONSENT CONTEXT (recording consent — reserved for future voice features)
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

// ═══════════════════════════════════════════════════════════════════
// ONBOARDING CONTEXT (Phase 2: first-launch flow)
// ═══════════════════════════════════════════════════════════════════

const ONBOARDING_KEY = '@maestro_onboarding_complete';

const OnboardingCtx = createContext<{
  hasOnboarded: boolean;
  completeOnboarding: () => void;
  resetOnboarding: () => void;
}>({ hasOnboarded: true, completeOnboarding: () => {}, resetOnboarding: () => {} });

export const useOnboarding = () => useContext(OnboardingCtx);

export function OnboardingProvider({ children }: { children: React.ReactNode }) {
  const [hasOnboarded, setHasOnboarded] = useState(true); // default true = skip for existing users

  useEffect(() => {
    AsyncStorage.getItem(ONBOARDING_KEY).then(v => {
      if (v !== 'true') setHasOnboarded(false);
    });
  }, []);

  const completeOnboarding = () => {
    setHasOnboarded(true);
    AsyncStorage.setItem(ONBOARDING_KEY, 'true');
  };

  const resetOnboarding = () => {
    setHasOnboarded(false);
    AsyncStorage.removeItem(ONBOARDING_KEY);
  };

  return <OnboardingCtx.Provider value={{ hasOnboarded, completeOnboarding, resetOnboarding }}>{children}</OnboardingCtx.Provider>;
}
