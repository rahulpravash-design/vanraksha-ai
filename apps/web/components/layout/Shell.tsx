"use client";

/** Authenticated shell: navigation, offline state, theme, sign-out. */

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { useAuth } from "@/lib/auth";
import { useTheme } from "@/lib/theme";
import { flush, onQueueChange, pendingCount } from "@/lib/offline";
import { Spinner } from "@/components/ui";
import type { Role } from "@/lib/types";

interface NavItem {
  href: string;
  label: string;
  roles?: Role[];
}

const NAV: NavItem[] = [
  { href: "/report", label: "Report" },
  { href: "/dashboard", label: "Dashboard" },
  {
    href: "/queue",
    label: "Queue",
    roles: ["field_worker", "veterinarian", "lab", "block_admin", "district_admin", "super_admin"],
  },
  {
    href: "/clusters",
    label: "Clusters",
    roles: ["field_worker", "veterinarian", "lab", "block_admin", "district_admin", "super_admin"],
  },
  { href: "/map", label: "Map" },
  {
    href: "/command",
    label: "Command",
    roles: ["block_admin", "district_admin", "super_admin"],
  },
];

export function Shell({ children }: { children: React.ReactNode }) {
  const { user, loading, signOut } = useAuth();
  const pathname = usePathname();
  const router = useRouter();

  useEffect(() => {
    if (!loading && !user) router.replace("/login");
  }, [loading, user, router]);

  if (loading) return <Spinner label="Checking your session" />;
  if (!user) return null;

  const items = NAV.filter((item) => !item.roles || item.roles.includes(user.role));

  return (
    <div className="min-h-screen">
      <header
        className="sticky top-0 z-40 border-b backdrop-blur"
        style={{ borderColor: "var(--border)", background: "color-mix(in srgb, var(--page) 88%, transparent)" }}
      >
        <div className="mx-auto flex max-w-6xl items-center gap-3 px-4 py-3">
          <Link href="/dashboard" className="flex shrink-0 items-center gap-2">
            <Mark />
            <span className="hidden text-sm font-semibold tracking-tight text-ink sm:block">
              VANRAKSHA
            </span>
          </Link>

          <nav className="flex flex-1 items-center gap-0.5 overflow-x-auto" aria-label="Main">
            {items.map((item) => {
              const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  aria-current={active ? "page" : undefined}
                  className="shrink-0 rounded-lg px-3 py-2 text-sm"
                  style={{
                    color: active ? "var(--text-primary)" : "var(--text-secondary)",
                    background: active ? "var(--surface-2)" : "transparent",
                    fontWeight: active ? 600 : 400,
                  }}
                >
                  {item.label}
                </Link>
              );
            })}
          </nav>

          <div className="flex shrink-0 items-center gap-1">
            <ConnectionState />
            <ThemeToggle />
            <button
              type="button"
              onClick={signOut}
              className="rounded-lg px-2.5 py-2 text-xs text-ink-secondary"
              title={`Signed in as ${user.full_name}`}
            >
              Sign out
            </button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-6xl px-4 py-6">{children}</main>

      <footer className="mx-auto max-w-6xl px-4 pb-10 pt-4">
        <p className="text-[11px] leading-relaxed text-ink-muted">
          VANRAKSHA AI supports veterinary decisions; it does not make clinical ones. It
          identifies syndromic patterns, scores urgency and detects clusters. Diagnosis and
          treatment remain with qualified veterinary and laboratory processes.
        </p>
      </footer>
    </div>
  );
}

function Mark() {
  return (
    <svg width="26" height="26" viewBox="0 0 64 64" aria-hidden="true">
      <path
        d="M32 12 L50 20 V33 C50 43 42 50 32 53 C22 50 14 43 14 33 V20 Z"
        fill="none" stroke="var(--series-1)" strokeWidth="3.5" strokeLinejoin="round"
      />
      <circle cx="32" cy="31" r="4.5" fill="var(--series-1)" />
    </svg>
  );
}

function ThemeToggle() {
  const { theme, toggle } = useTheme();
  return (
    <button
      type="button"
      onClick={toggle}
      className="rounded-lg px-2.5 py-2 text-ink-secondary"
      aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} theme`}
      title={`Switch to ${theme === "dark" ? "light" : "dark"} theme`}
    >
      {theme === "dark" ? "☀" : "☽"}
    </button>
  );
}

/**
 * Connection and queue state.
 *
 * This is load-bearing rather than decorative: a farmer who cannot tell whether
 * a report was sent will either file it twice or assume it went and walk away.
 */
function ConnectionState() {
  const [online, setOnline] = useState(true);
  const [queued, setQueued] = useState(0);
  const [syncing, setSyncing] = useState(false);

  useEffect(() => {
    setOnline(navigator.onLine);
    const refresh = () => pendingCount().then(setQueued);
    refresh();

    const goOnline = async () => {
      setOnline(true);
      setSyncing(true);
      await flush().catch(() => undefined);
      setSyncing(false);
      refresh();
    };
    const goOffline = () => setOnline(false);

    window.addEventListener("online", goOnline);
    window.addEventListener("offline", goOffline);
    const unsubscribe = onQueueChange(refresh);
    return () => {
      window.removeEventListener("online", goOnline);
      window.removeEventListener("offline", goOffline);
      unsubscribe();
    };
  }, []);

  if (online && queued === 0 && !syncing) return null;

  const label = syncing
    ? "Sending…"
    : !online
      ? queued > 0
        ? `Offline · ${queued} saved`
        : "Offline"
      : `${queued} to send`;

  return (
    <span
      className="flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px]"
      style={{
        borderColor: online ? "var(--border)" : "var(--status-warning)",
        color: online ? "var(--text-secondary)" : "var(--status-warning)",
      }}
      role="status"
    >
      <span aria-hidden="true">{online ? "↻" : "⚡"}</span>
      {label}
    </span>
  );
}
