import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import type { Account, AccountResponse, PlanLimits } from './hawkvance-api.js';
import { ApiRejected, HawkVanceApi } from './hawkvance-api.js';
import { NeonAuthClient } from './neon-auth.js';

/// Holds only the short-lived identity token, and only in memory.
///
/// The Neon session lives in the Rust core and is kept in the encrypted vault between runs, so
/// closing the app no longer signs anybody out. Only signing out does, and that erases it.

export type SessionState =
  | { readonly kind: 'restoring' }
  | { readonly kind: 'signedOut' }
  | { readonly kind: 'signedIn'; readonly account: Account; readonly limits: PlanLimits };

export class SessionExpired extends Error {
  constructor() {
    super('You have been signed out. Please sign in again.');
    this.name = 'SessionExpired';
  }
}

type SessionContextValue = {
  readonly state: SessionState;
  readonly api: HawkVanceApi;
  readonly adoptIdentityToken: (token: string) => Promise<void>;
  readonly signOut: () => Promise<void>;
  readonly updateProfile: (fields: {
    displayName?: string;
    occupation?: string | null;
  }) => Promise<void>;
  readonly withIdentityToken: <TResult>(
    use: (token: string) => Promise<TResult>,
  ) => Promise<TResult>;
};

const SessionContext = createContext<SessionContextValue | null>(null);

export function SessionProvider({ children }: { children: ReactNode }): JSX.Element {
  const api = useMemo(() => new HawkVanceApi(), []);
  const [state, setState] = useState<SessionState>({ kind: 'restoring' });
  const identityToken = useRef<string | null>(null);

  const loadAccount = useCallback(
    async (token: string): Promise<void> => {
      const current: AccountResponse = await api.currentAccount(token);
      identityToken.current = token;
      setState({ kind: 'signedIn', account: current.account, limits: current.limits });
    },
    [api],
  );

  const adoptIdentityToken = useCallback(
    async (token: string): Promise<void> => {
      await loadAccount(token);
    },
    [loadAccount],
  );

  const signOut = useCallback(async (): Promise<void> => {
    await NeonAuthClient.signOut();
    identityToken.current = null;
    setState({ kind: 'signedOut' });
  }, []);

  /// Mints a new token from the session held in Rust.
  const renew = useCallback(async (): Promise<string> => {
    try {
      const token = await NeonAuthClient.identityToken();
      identityToken.current = token;
      return token;
    } catch {
      identityToken.current = null;
      setState({ kind: 'signedOut' });
      throw new SessionExpired();
    }
  }, []);

  /// Runs a call with a valid token, renewing once if the backend says it has aged out.
  ///
  /// The retry is deliberately narrow: only a 401, and only once. Anything else, including being
  /// unable to reach the server at all, is passed straight through, because retrying those would
  /// turn a clear failure into a confusing one.
  const withIdentityToken = useCallback(
    async <TResult,>(use: (token: string) => Promise<TResult>): Promise<TResult> => {
      const held = identityToken.current;
      if (held !== null) {
        try {
          return await use(held);
        } catch (cause) {
          if (!(cause instanceof ApiRejected) || cause.status !== 401) {
            throw cause;
          }
        }
      }
      return use(await renew());
    },
    [renew],
  );

  const updateProfile = useCallback(
    async (fields: { displayName?: string; occupation?: string | null }): Promise<void> => {
      // The reply carries the whole account back, so the local copy is replaced with what the
      // server actually stored rather than with what was submitted. Those differ whenever it
      // trims, rejects or normalises something.
      const updated = await withIdentityToken(async (token) => api.updateProfile(token, fields));
      setState({ kind: 'signedIn', account: updated.account, limits: updated.limits });
    },
    [api, withIdentityToken],
  );

  useEffect(() => {
    let cancelled = false;
    const restore = async (): Promise<void> => {
      const token = await NeonAuthClient.restore();
      if (cancelled) {
        return;
      }
      if (token === null) {
        setState({ kind: 'signedOut' });
        return;
      }
      try {
        await loadAccount(token);
      } catch {
        if (!cancelled) {
          setState({ kind: 'signedOut' });
        }
      }
    };
    void restore();
    return () => {
      cancelled = true;
    };
  }, [loadAccount]);

  const value = useMemo(
    () => ({ state, api, adoptIdentityToken, signOut, updateProfile, withIdentityToken }),
    [state, api, adoptIdentityToken, signOut, updateProfile, withIdentityToken],
  );

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession(): SessionContextValue & {
  readonly account: Account;
  readonly limits: PlanLimits;
} {
  const context = useContext(SessionContext);
  if (context === null) {
    throw new Error('useSession was called outside the session provider');
  }
  if (context.state.kind !== 'signedIn') {
    throw new Error('useSession was called before anybody signed in');
  }
  return { ...context, account: context.state.account, limits: context.state.limits };
}

/// For the parts of the app that run before sign-in, where there is no account yet.
export function useSessionState(): SessionContextValue {
  const context = useContext(SessionContext);
  if (context === null) {
    throw new Error('useSessionState was called outside the session provider');
  }
  return context;
}
