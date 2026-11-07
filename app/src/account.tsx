import AsyncStorage from '@react-native-async-storage/async-storage';
import { useQueryClient } from '@tanstack/react-query';
import * as AppleAuthentication from 'expo-apple-authentication';
import * as SecureStore from 'expo-secure-store';
import { createContext, ReactNode, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { Platform } from 'react-native';

import { API_URL, USE_SAMPLE } from './api';

// Accounts exist only for friend groups. Signing in is Sign in with Apple; the server swaps Apple's
// identity token for its own session token, kept in the keychain.

const TOKEN_KEY = 'session-token';
const ME_KEY = 'account-me'; // last known profile, so the app still knows you're signed in when offline

export type Me = { name: string; needs_name: boolean };

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
  }
}

const tokenStore = {
  get: () => (Platform.OS === 'web' ? AsyncStorage.getItem(TOKEN_KEY) : SecureStore.getItemAsync(TOKEN_KEY)),
  set: (v: string) => (Platform.OS === 'web' ? AsyncStorage.setItem(TOKEN_KEY, v) : SecureStore.setItemAsync(TOKEN_KEY, v)),
  clear: () => (Platform.OS === 'web' ? AsyncStorage.removeItem(TOKEN_KEY) : SecureStore.deleteItemAsync(TOKEN_KEY)),
};

async function request<T>(method: string, path: string, token: string | null, body?: unknown): Promise<T> {
  if (USE_SAMPLE) {
    const { sampleSocial } = await import('./sample/social');
    return sampleSocial(method, path, body) as T;
  }
  const res = await fetch(`${API_URL}${path}`, {
    method,
    headers: {
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(body !== undefined ? { 'Content-Type': 'application/json' } : {}),
    },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = typeof data?.detail === 'string' ? data.detail : 'Something went wrong. Try again.';
    throw new ApiError(detail, res.status);
  }
  return data as T;
}

type AccountState = {
  ready: boolean;
  signedIn: boolean;
  me: Me | null;
  appleAvailable: boolean;
  signIn: () => Promise<void>;
  signOut: () => Promise<void>;
  setName: (name: string) => Promise<void>;
  deleteAccount: () => Promise<void>;
  call: <T>(method: string, path: string, body?: unknown) => Promise<T>;
};

const AccountContext = createContext<AccountState | null>(null);

export function AccountProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const [ready, setReady] = useState(false);
  const [token, setToken] = useState<string | null>(null);
  const [me, setMe] = useState<Me | null>(null);
  const [appleAvailable, setAppleAvailable] = useState(USE_SAMPLE);

  const signOut = useCallback(async () => {
    await tokenStore.clear().catch(() => {});
    setToken(null);
    setMe(null);
    queryClient.removeQueries({ queryKey: ['social'] });
  }, [queryClient]);

  const call = useCallback(
    async <T,>(method: string, path: string, body?: unknown) => {
      try {
        return await request<T>(method, path, token, body);
      } catch (e) {
        if (e instanceof ApiError && e.status === 401) await signOut();
        throw e;
      }
    },
    [token, signOut],
  );

  useEffect(() => {
    if (!USE_SAMPLE) AppleAuthentication.isAvailableAsync().then(setAppleAvailable).catch(() => {});
    (async () => {
      const saved = USE_SAMPLE ? 'sample' : await tokenStore.get().catch(() => null);
      if (saved) {
        setToken(saved);
        try {
          setMe(await request<Me>('GET', '/me', saved));
        } catch (e) {
          if (e instanceof ApiError && e.status === 401) {
            await tokenStore.clear().catch(() => {});
            setToken(null);
          } else {
            const cached = await AsyncStorage.getItem(ME_KEY).catch(() => null);
            if (cached) setMe(JSON.parse(cached) as Me);
          }
        }
      }
      setReady(true);
    })();
  }, []);

  const signIn = useCallback(async () => {
    let identityToken = 'sample';
    let name: string | null = null;
    if (!USE_SAMPLE) {
      const cred = await AppleAuthentication.signInAsync({
        requestedScopes: [AppleAuthentication.AppleAuthenticationScope.FULL_NAME],
      });
      if (!cred.identityToken) throw new Error('Apple sign-in did not return a token.');
      identityToken = cred.identityToken;
      name = [cred.fullName?.givenName, cred.fullName?.familyName].filter(Boolean).join(' ') || null;
    }
    const res = await request<{ token: string; user: Me }>('POST', '/auth/apple', null, { identity_token: identityToken, name });
    await tokenStore.set(res.token);
    setToken(res.token);
    setMe(res.user);
  }, []);

  const setName = useCallback(async (name: string) => setMe(await call<Me>('PATCH', '/me', { name })), [call]);

  const deleteAccount = useCallback(async () => {
    await call('DELETE', '/me');
    await signOut();
  }, [call, signOut]);

  useEffect(() => {
    if (me) AsyncStorage.setItem(ME_KEY, JSON.stringify(me)).catch(() => {});
    else if (ready) AsyncStorage.removeItem(ME_KEY).catch(() => {});
  }, [me, ready]);

  const value = useMemo(
    () => ({ ready, signedIn: !!token && !!me, me, appleAvailable, signIn, signOut, setName, deleteAccount, call }),
    [ready, token, me, appleAvailable, signIn, signOut, setName, deleteAccount, call],
  );
  return <AccountContext.Provider value={value}>{children}</AccountContext.Provider>;
}

export function useAccount(): AccountState {
  const ctx = useContext(AccountContext);
  if (!ctx) throw new Error('useAccount must be used inside AccountProvider');
  return ctx;
}

/** True when the user cancelled the Apple sheet, which isn't an error worth showing. */
export function isCancel(e: unknown): boolean {
  return (e as { code?: string })?.code === 'ERR_REQUEST_CANCELED';
}
