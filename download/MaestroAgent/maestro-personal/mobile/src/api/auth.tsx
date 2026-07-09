/**
 * Auth context — manages the bearer token via AsyncStorage.
 *
 * The mobile app stores the token after login and includes it in all
 * API requests. Logout clears the token.
 */

import React, { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { login as apiLogin } from '../api/client';

const TOKEN_KEY = '@maestro_personal_token';

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
    // Load token from storage on mount
    AsyncStorage.getItem(TOKEN_KEY).then((stored) => {
      setToken(stored);
      setIsLoading(false);
    });
  }, []);

  const login = async (password: string) => {
    const result = await apiLogin(password);
    setToken(result.token);
    await AsyncStorage.setItem(TOKEN_KEY, result.token);
  };

  const logout = async () => {
    setToken(null);
    await AsyncStorage.removeItem(TOKEN_KEY);
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
