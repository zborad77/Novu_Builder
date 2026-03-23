import React, { createContext, useContext, useEffect, useState } from 'react';
import { AuthApi, TokenStorage } from '../services/api';
import type { AuthUser } from '../types';

interface AuthState {
  user: AuthUser | null;
  isLoading: boolean;
  isAuthenticated: boolean;
}

interface AuthContextValue extends AuthState {
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<AuthState>({
    user: null,
    isLoading: true,
    isAuthenticated: false,
  });

  useEffect(() => {
    TokenStorage.getAccessToken().then((token) => {
      if (token) {
        // Token exists — we trust it until first 401
        // In a real app you'd call /auth/me here
        setState((s) => ({ ...s, isLoading: false, isAuthenticated: true }));
      } else {
        setState((s) => ({ ...s, isLoading: false }));
      }
    });
  }, []);

  async function login(email: string, password: string) {
    const res = await AuthApi.login(email, password);
    await TokenStorage.setTokens(res.accessToken, res.refreshToken);
    setState({ user: res.user, isLoading: false, isAuthenticated: true });
  }

  async function logout() {
    const refreshToken = await TokenStorage.getRefreshToken();
    if (refreshToken) await AuthApi.logout(refreshToken);
    await TokenStorage.clearTokens();
    setState({ user: null, isLoading: false, isAuthenticated: false });
  }

  return (
    <AuthContext.Provider value={{ ...state, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}
