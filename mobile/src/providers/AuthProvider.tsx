import * as SecureStore from 'expo-secure-store';
import { PropsWithChildren, createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { Platform } from 'react-native';

import { api, User } from '@/lib/api';

const TOKEN_KEY = 'carerelay.access-token';

type AuthContextValue = {
  token: string | null;
  user: User | null;
  loading: boolean;
  initializationError: string | null;
  retryInitialization: () => void;
  signIn: (email: string, displayName: string) => Promise<void>;
  signInWithApple: (identityToken: string, nonce: string, displayName?: string) => Promise<void>;
  signOut: () => Promise<void>;
  deleteAccount: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

async function readToken(): Promise<string | null> {
  if (Platform.OS === 'web') return globalThis.localStorage?.getItem(TOKEN_KEY) ?? null;
  return SecureStore.getItemAsync(TOKEN_KEY);
}

async function writeToken(token: string | null): Promise<void> {
  if (Platform.OS === 'web') {
    if (token) globalThis.localStorage?.setItem(TOKEN_KEY, token);
    else globalThis.localStorage?.removeItem(TOKEN_KEY);
    return;
  }
  if (token) await SecureStore.setItemAsync(TOKEN_KEY, token);
  else await SecureStore.deleteItemAsync(TOKEN_KEY);
}

export function AuthProvider({ children }: PropsWithChildren) {
  const [token, setToken] = useState<string | null>(null);
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [initializationError, setInitializationError] = useState<string | null>(null);
  const [initializationAttempt, setInitializationAttempt] = useState(0);

  useEffect(() => {
    let active = true;
    setInitializationError(null);
    setLoading(true);
    readToken()
      .then(async (storedToken) => {
        if (!storedToken) return;
        const currentUser = await api.me(storedToken);
        if (active) {
          setToken(storedToken);
          setUser(currentUser);
        }
      })
      .catch(() => {
        if (active) setInitializationError('We could not restore your session. Check your connection and try again.');
      })
      .finally(() => active && setLoading(false));
    return () => {
      active = false;
    };
  }, [initializationAttempt]);

  const retryInitialization = useCallback(() => {
    setInitializationAttempt((current) => current + 1);
  }, []);

  const signIn = useCallback(async (email: string, displayName: string) => {
    setInitializationError(null);
    const result = await api.devLogin(email.trim(), displayName.trim());
    await writeToken(result.access_token);
    setToken(result.access_token);
    setUser(result.user);
  }, []);

  const signInWithApple = useCallback(async (
    identityToken: string,
    nonce: string,
    displayName?: string,
  ) => {
    setInitializationError(null);
    const result = await api.appleLogin(identityToken, nonce, displayName);
    await writeToken(result.access_token);
    setToken(result.access_token);
    setUser(result.user);
  }, []);

  const signOut = useCallback(async () => {
    await writeToken(null);
    setToken(null);
    setUser(null);
  }, []);

  const deleteAccount = useCallback(async () => {
    if (!token) return;
    await api.deleteAccount(token);
    await writeToken(null);
    setToken(null);
    setUser(null);
  }, [token]);

  const value = useMemo(
    () => ({
      token,
      user,
      loading,
      initializationError,
      retryInitialization,
      signIn,
      signInWithApple,
      signOut,
      deleteAccount,
    }),
    [
      token,
      user,
      loading,
      initializationError,
      retryInitialization,
      signIn,
      signInWithApple,
      signOut,
      deleteAccount,
    ],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const value = useContext(AuthContext);
  if (!value) throw new Error('useAuth must be used inside AuthProvider');
  return value;
}
