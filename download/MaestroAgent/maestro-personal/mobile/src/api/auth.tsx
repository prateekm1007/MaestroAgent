/**
 * Auth context — manages the bearer token via SecureStore.
 *
 * Phase 1 security fix: token stored in SecureStore (expo-secure-store),
 * NOT AsyncStorage. SecureStore uses iOS Keychain / Android Keystore
 * (encrypted at rest). AsyncStorage is plaintext JSON on disk.
 *
 * The mobile app stores the token after login and includes it in all
 * API requests. Logout clears the token and calls POST /api/auth/revoke.
 */

import React, { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import * as SecureStore from 'expo-secure-store';
import { login as apiLogin, getHost } from '../api/client';

const TOKEN_KEY = 'maestro_token';

interface AuthContextType {
  token: string | null;
  isLoading: boolean;
  login: (password: string) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    // Load token from SecureStore on mount
    SecureStore.getItemAsync(TOKEN_KEY).then((stored) => {
      setToken(stored);
      setIsLoading(false);
    }).catch(() => {
      setIsLoading(false);
    });
  }, []);

  const login = async (password: string) => {
    const result = await apiLogin(password);
    setToken(result.token);
    await SecureStore.setItemAsync(TOKEN_KEY, result.token);
  };

  const logout = async () => {
    // Best-effort revoke on server (non-fatal if it fails)
    try {
      await fetch(`${getHost()}/api/auth/revoke`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` },
      });
    } catch {
      // Server may be down — still clear local token
    }
    setToken(null);
    try {
      await SecureStore.deleteItemAsync(TOKEN_KEY);
    } catch {
      // ignore
    }
  };

  return (
    <AuthContext.Provider value={{ token, isLoading, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextType {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within AuthProvider');
  }
  return context;
}
