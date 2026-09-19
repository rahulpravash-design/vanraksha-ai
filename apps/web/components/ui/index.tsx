"use client";

/** Interface primitives. Deliberately small and hand-rolled. */

import type { ReactNode } from "react";

import { BAND_LABEL, BAND_STATUS, type Band, isBand } from "@/lib/bands";

export function Card({
  children, className = "", padded = true,
}: { children: ReactNode; className?: string; padded?: boolean }) {
  return (
    <section
      className={`rounded-card border bg-surface ${padded ? "p-5" : ""} ${className}`}
      style={{ borderColor: "var(--border)" }}
    >
      {children}
    </section>
  );
}

export function CardHeader({
  title, subtitle, action,
}: { title: string; subtitle?: string; action?: ReactNode }) {
  return (
    <header className="mb-4 flex items-start justify-between gap-4">
      <div>
        <h2 className="text-sm font-semibold text-ink">{title}</h2>
        {subtitle ? (
          <p className="mt-0.5 text-xs text-ink-muted">{subtitle}</p>
        ) : null}
      </div>
      {action}
    </header>
  );
}

/**
 * A triage band. The label is always rendered, so the colour supplements the
 * text rather than carrying the meaning on its own -- which is what keeps it
 * readable for a colourblind reader, in sunlight, and in a printed report.
 */
export function BandBadge({ band, size = "md" }: { band: string; size?: "sm" | "md" }) {
  const key: Band = isBand(band) ? band : "routine";
  const status = BAND_STATUS[key];
  const padding = size === "sm" ? "px-2 py-0.5 text-[11px]" : "px-2.5 py-1 text-xs";

  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border font-medium ${padding}`}
      style={{
        borderColor: status.color,
        color: status.solid ? "var(--surface-1)" : status.color,
        backgroundColor: status.solid ? status.color : "transparent",
      }}
    >
      <span aria-hidden="true">{status.glyph}</span>
      {BAND_LABEL[key]}
    </span>
  );
}

export function Button({
  children, onClick, variant = "primary", type = "button", disabled, className = "", full,
}: {
  children: ReactNode;
  onClick?: () => void;
  variant?: "primary" | "secondary" | "ghost" | "danger";
  type?: "button" | "submit";
  disabled?: boolean;
  className?: string;
  full?: boolean;
}) {
  const styles: Record<string, string> = {
    primary: "text-white",
    secondary: "border text-ink",
    ghost: "text-ink-secondary",
    danger: "text-white",
  };
  const background: Record<string, string> = {
    primary: "var(--series-1)",
    secondary: "transparent",
    ghost: "transparent",
    danger: "var(--status-critical)",
  };

  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      className={`inline-flex min-h-[44px] items-center justify-center gap-2 rounded-lg px-4 text-sm font-medium transition-opacity disabled:cursor-not-allowed disabled:opacity-45 ${styles[variant]} ${full ? "w-full" : ""} ${className}`}
      style={{
        backgroundColor: background[variant],
        borderColor: variant === "secondary" ? "var(--border)" : undefined,
      }}
    >
      {children}
    </button>
  );
}

export function Field({
  label, hint, error, children, required,
}: {
  label: string;
  hint?: string;
  error?: string;
  children: ReactNode;
  required?: boolean;
}) {
  return (
    <label className="block">
      <span className="mb-1.5 flex items-baseline gap-1.5 text-sm font-medium text-ink">
        {label}
        {required ? <span className="text-xs text-ink-muted">(required)</span> : null}
      </span>
      {children}
      {error ? (
        <span
          className="mt-1.5 flex items-start gap-1.5 text-xs"
          style={{ color: "var(--status-critical)" }}
          role="alert"
        >
          <span aria-hidden="true">&#9679;</span>
          {error}
        </span>
      ) : hint ? (
        <span className="mt-1.5 block text-xs text-ink-muted">{hint}</span>
      ) : null}
    </label>
  );
}

export const inputClass =
  "w-full min-h-[44px] rounded-lg border bg-surface-2 px-3 text-sm text-ink placeholder:text-ink-muted";
export const inputStyle = { borderColor: "var(--border)" } as const;

/**
 * A single headline number. The right form when the story is one figure --
 * a one-bar bar chart is not a chart.
 */
export function StatTile({
  label, value, delta, note, tone = "neutral",
}: {
  label: string;
  value: string;
  delta?: { text: string; direction: "up" | "down" | "flat"; good?: boolean };
  note?: string;
  tone?: "neutral" | "critical";
}) {
  return (
    <div
      className="rounded-card border bg-surface p-4"
      style={{ borderColor: "var(--border)" }}
    >
      <p className="text-xs text-ink-secondary">{label}</p>
      <p
        className="mt-1.5 text-3xl font-semibold leading-none"
        style={{ color: tone === "critical" ? "var(--status-critical)" : "var(--text-primary)" }}
      >
        {value}
      </p>
      {delta ? (
        <p
          className="mt-2 text-xs"
          style={{
            color:
              delta.direction === "flat"
                ? "var(--text-muted)"
                : delta.good
                  ? "var(--success-text)"
                  : "var(--status-critical)",
          }}
        >
          <span aria-hidden="true">
            {delta.direction === "up" ? "↑" : delta.direction === "down" ? "↓" : "→"}
          </span>{" "}
          {delta.text}
        </p>
      ) : null}
      {note ? <p className="mt-2 text-xs text-ink-muted">{note}</p> : null}
    </div>
  );
}

export function EmptyState({ title, body, action }: { title: string; body: string; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 px-6 py-12 text-center">
      <p className="text-sm font-medium text-ink">{title}</p>
      <p className="max-w-sm text-xs text-ink-muted">{body}</p>
      {action ? <div className="mt-2">{action}</div> : null}
    </div>
  );
}

export function Spinner({ label = "Loading" }: { label?: string }) {
  return (
    <div className="flex items-center justify-center gap-2 py-10 text-xs text-ink-muted">
      <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true">
        <circle
          cx="8" cy="8" r="6" fill="none" strokeWidth="2"
          stroke="var(--border)"
        />
        <path
          d="M14 8a6 6 0 0 0-6-6" fill="none" strokeWidth="2" strokeLinecap="round"
          stroke="var(--series-1)"
        >
          <animateTransform
            attributeName="transform" type="rotate" from="0 8 8" to="360 8 8"
            dur="0.9s" repeatCount="indefinite"
          />
        </path>
      </svg>
      {label}
    </div>
  );
}

export function Notice({
  tone, title, children,
}: {
  tone: "info" | "warning" | "critical";
  title: string;
  children?: ReactNode;
}) {
  const colour = {
    info: "var(--series-1)",
    warning: "var(--status-warning)",
    critical: "var(--status-critical)",
  }[tone];
  const glyph = { info: "ℹ", warning: "⚠", critical: "⚠" }[tone];

  return (
    <div
      className="rounded-card border-l-4 bg-surface p-4"
      style={{ borderLeftColor: colour, boxShadow: "inset 0 0 0 1px var(--border)" }}
      role={tone === "critical" ? "alert" : undefined}
    >
      <p className="flex items-center gap-2 text-sm font-semibold text-ink">
        <span aria-hidden="true" style={{ color: colour }}>{glyph}</span>
        {title}
      </p>
      {children ? <div className="mt-2 text-xs text-ink-secondary">{children}</div> : null}
    </div>
  );
}
