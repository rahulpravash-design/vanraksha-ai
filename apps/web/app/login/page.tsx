"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { Button, Field, inputClass, inputStyle } from "@/components/ui";

const DEMO_ACCOUNTS = [
  { email: "farmer1@example.org", role: "Farmer", what: "files reports, sees only their own herd" },
  { email: "vet.hoskote@example.org", role: "Veterinarian", what: "works the case queue, reviews clusters" },
  { email: "district@example.org", role: "District officer", what: "district aggregates, runs the sweep" },
];
const DEMO_PASSWORD = "VanrakshaDemo2026!";

export default function LoginPage() {
  const { signIn, user } = useAuth();
  const router = useRouter();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (user) router.replace("/dashboard");
  }, [user, router]);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await signIn(email.trim(), password);
      router.replace("/dashboard");
    } catch (cause) {
      setError(
        cause instanceof ApiError
          ? cause.message
          : "Sign-in failed. Please try again.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto flex min-h-screen max-w-md flex-col justify-center px-6 py-12">
      <Link href="/" className="mb-8 flex items-center gap-2.5">
        <svg width="28" height="28" viewBox="0 0 64 64" aria-hidden="true">
          <path
            d="M32 12 L50 20 V33 C50 43 42 50 32 53 C22 50 14 43 14 33 V20 Z"
            fill="none" stroke="var(--series-1)" strokeWidth="3.5" strokeLinejoin="round"
          />
          <circle cx="32" cy="31" r="4.5" fill="var(--series-1)" />
        </svg>
        <span className="text-sm font-semibold tracking-tight">VANRAKSHA AI</span>
      </Link>

      <h1 className="text-2xl font-semibold tracking-tight">Sign in</h1>
      <p className="mt-1.5 text-sm text-ink-secondary">
        Your role decides what you can see and do.
      </p>

      <form onSubmit={submit} className="mt-8 space-y-4">
        <Field label="Email" required>
          <input
            type="email" value={email} required autoComplete="username"
            onChange={(event) => setEmail(event.target.value)}
            className={inputClass} style={inputStyle}
            placeholder="you@example.org"
          />
        </Field>

        <Field label="Password" required>
          <input
            type="password" value={password} required autoComplete="current-password"
            onChange={(event) => setPassword(event.target.value)}
            className={inputClass} style={inputStyle}
          />
        </Field>

        {error ? (
          <p
            className="flex items-start gap-2 rounded-lg px-3 py-2.5 text-xs"
            style={{
              color: "var(--status-critical)",
              background: "color-mix(in srgb, var(--status-critical) 8%, transparent)",
            }}
            role="alert"
          >
            <span aria-hidden="true">&#9679;</span>
            {error}
          </p>
        ) : null}

        <Button type="submit" full disabled={busy}>
          {busy ? "Signing in…" : "Sign in"}
        </Button>
      </form>

      <section
        className="mt-10 rounded-card border p-4"
        style={{ borderColor: "var(--border)" }}
      >
        <h2 className="text-xs font-semibold text-ink">Demonstration accounts</h2>
        <p className="mt-1 text-[11px] leading-relaxed text-ink-muted">
          Available after seeding the demo dataset. All of its livestock data is synthetic.
        </p>
        <ul className="mt-3 space-y-2">
          {DEMO_ACCOUNTS.map((account) => (
            <li key={account.email}>
              <button
                type="button"
                onClick={() => {
                  setEmail(account.email);
                  setPassword(DEMO_PASSWORD);
                }}
                className="w-full rounded-lg border px-3 py-2 text-left text-[11px] transition-colors"
                style={{ borderColor: "var(--border)" }}
              >
                <span className="font-medium text-ink">{account.role}</span>
                <span className="ml-1.5 text-ink-muted">{account.what}</span>
                <span className="mt-0.5 block font-mono text-[10px] text-ink-muted">
                  {account.email}
                </span>
              </button>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
