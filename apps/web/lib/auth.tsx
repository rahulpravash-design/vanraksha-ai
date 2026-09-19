"use client";

/** Session state, shared across the authenticated shell. */

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import { api, getToken, setToken } from "./api";
import type { Role, User } from "./types";

interface AuthValue {
  user: User | null;
  loading: boolean;
  signIn: (email: string, password: string) => Promise<void>;
  signOut: () => void;
  hasRole: (...roles: Role[]) => boolean;
  isStaff: boolean;
}

const AuthContext = createContext<AuthValue | null>(null);

const STAFF_ROLES: Role[] = [
  "field_worker", "veterinarian", "lab", "block_admin", "district_admin", "super_admin",
];

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const router = useRouter();

  useEffect(() => {
    let cancelled = false;
    if (!getToken()) {
      setLoading(false);
      return;
    }
    api
      .me()
      .then((me) => {
        if (!cancelled) setUser(me);
      })
      .catch(() => {
        // An expired or revoked token should not leave the app in a half-signed-in
        // state; clear it and let the shell redirect.
        setToken(null);
        if (!cancelled) setUser(null);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const signIn = useCallback(async (email: string, password: string) => {
    await api.login(email, password);
    setUser(await api.me());
  }, []);

  const signOut = useCallback(() => {
    api.logout();
    setUser(null);
    router.push("/login");
  }, [router]);

  const value = useMemo<AuthValue>(
    () => ({
      user,
      loading,
      signIn,
      signOut,
      hasRole: (...roles: Role[]) => (user ? roles.includes(user.role) : false),
      isStaff: user ? STAFF_ROLES.includes(user.role) : false,
    }),
    [user, loading, signIn, signOut],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthValue {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside <AuthProvider>");
  return context;
}
