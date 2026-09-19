/**
 * Triage bands, and how they are presented.
 *
 * Band colour is never the only carrier of meaning: every badge renders its
 * label, and the two status roles that fall below 3:1 on the light surface are
 * paired with a glyph. The chart ramp is a separate, ordinal scale -- severity
 * is ordered, so it gets one hue stepped light-to-dark rather than five
 * unrelated categorical hues.
 */

export const BANDS = ["routine", "monitor", "priority", "urgent", "emergency"] as const;
export type Band = (typeof BANDS)[number];

export const BAND_RANK: Record<Band, number> = {
  routine: 0,
  monitor: 1,
  priority: 2,
  urgent: 3,
  emergency: 4,
};

export const BAND_LABEL: Record<Band, string> = {
  routine: "Routine",
  monitor: "Monitor",
  priority: "Priority",
  urgent: "Urgent",
  emergency: "Emergency",
};

/** The ordinal ramp, for charts. Matches --band-* in globals.css. */
export const BAND_RAMP: Record<Band, string> = {
  routine: "var(--band-routine)",
  monitor: "var(--band-monitor)",
  priority: "var(--band-priority)",
  urgent: "var(--band-urgent)",
  emergency: "var(--band-emergency)",
};

/** Status role, for badges in the interface. Always beside a text label. */
export const BAND_STATUS: Record<Band, { color: string; glyph: string; solid: boolean }> = {
  routine: { color: "var(--text-muted)", glyph: "○", solid: false },
  monitor: { color: "var(--status-warning)", glyph: "◔", solid: false },
  priority: { color: "var(--status-serious)", glyph: "◑", solid: false },
  urgent: { color: "var(--status-critical)", glyph: "◕", solid: false },
  emergency: { color: "var(--status-critical)", glyph: "●", solid: true },
};

export const BAND_RESPONSE_HOURS: Record<Band, number> = {
  routine: 168,
  monitor: 72,
  priority: 24,
  urgent: 6,
  emergency: 2,
};

export function isBand(value: string): value is Band {
  return (BANDS as readonly string[]).includes(value);
}

export function bandRank(value: string): number {
  return isBand(value) ? BAND_RANK[value] : -1;
}

/** Bands at which a veterinary case is opened. */
export function isEscalated(value: string): boolean {
  return bandRank(value) >= BAND_RANK.priority;
}

export const SYNDROME_LABEL: Record<string, string> = {
  respiratory: "Respiratory",
  enteric: "Digestive / enteric",
  vesicular: "Vesicular",
  neurological: "Neurological",
  systemic: "Systemic / febrile",
  reproductive: "Reproductive",
  udder: "Udder / mastitis",
  skin: "Skin",
  locomotor: "Locomotor",
  sudden_death: "Sudden death",
  production: "Production drop",
};

export function syndromeLabel(code: string | null | undefined): string {
  if (!code) return "Mixed";
  return SYNDROME_LABEL[code] ?? code.replace(/_/g, " ");
}
