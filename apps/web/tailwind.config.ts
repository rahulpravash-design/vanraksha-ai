import type { Config } from "tailwindcss";

/**
 * Colours are not defined here. They live as CSS custom properties in
 * globals.css so that light and dark are two selected palettes rather than an
 * automatic flip, and so the chart components read the same tokens as the rest
 * of the interface. Tailwind maps names onto those variables.
 */
export default {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        page: "var(--page)",
        surface: "var(--surface-1)",
        "surface-2": "var(--surface-2)",
        ink: "var(--text-primary)",
        "ink-secondary": "var(--text-secondary)",
        "ink-muted": "var(--text-muted)",
        hairline: "var(--border)",
        grid: "var(--grid)",
        axis: "var(--axis)",
        accent: "var(--series-1)",
        good: "var(--status-good)",
        warning: "var(--status-warning)",
        serious: "var(--status-serious)",
        critical: "var(--status-critical)",
      },
      fontFamily: {
        sans: ["system-ui", "-apple-system", "Segoe UI", "sans-serif"],
      },
      borderRadius: { card: "14px" },
    },
  },
  plugins: [],
} satisfies Config;
