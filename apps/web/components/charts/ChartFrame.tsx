"use client";

/**
 * Shared chrome for every chart.
 *
 * Carries the one accessibility guarantee that applies to all of them: a table
 * view is always reachable, so no value is gated behind seeing a colour or
 * hovering a mark.
 */

import { useState, type ReactNode } from "react";

export interface TableSpec {
  columns: string[];
  rows: (string | number)[][];
}

export function ChartFrame({
  title, subtitle, table, children, footer,
}: {
  title: string;
  subtitle?: string;
  table: TableSpec;
  children: ReactNode;
  footer?: ReactNode;
}) {
  const [showTable, setShowTable] = useState(false);

  return (
    <section
      className="rounded-card border bg-surface p-5"
      style={{ borderColor: "var(--border)" }}
    >
      <header className="mb-4 flex items-start justify-between gap-4">
        <div>
          <h2 className="text-sm font-semibold text-ink">{title}</h2>
          {subtitle ? <p className="mt-0.5 text-xs text-ink-muted">{subtitle}</p> : null}
        </div>
        <button
          type="button"
          onClick={() => setShowTable((value) => !value)}
          className="shrink-0 rounded-md border px-2.5 py-1 text-[11px] text-ink-secondary"
          style={{ borderColor: "var(--border)" }}
          aria-pressed={showTable}
        >
          {showTable ? "Chart" : "Table"}
        </button>
      </header>

      {showTable ? (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs tabular">
            <thead>
              <tr className="text-ink-muted">
                {table.columns.map((column) => (
                  <th key={column} className="border-b py-2 pr-4 font-medium"
                      style={{ borderColor: "var(--border)" }}>
                    {column}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {table.rows.map((row, index) => (
                <tr key={index} className="text-ink-secondary">
                  {row.map((cell, cellIndex) => (
                    <td key={cellIndex} className="border-b py-2 pr-4"
                        style={{ borderColor: "var(--border)" }}>
                      {cell}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        children
      )}

      {footer ? <div className="mt-3 text-xs text-ink-muted">{footer}</div> : null}
    </section>
  );
}

/** Rounded at the value end, square at the baseline. */
export function barPath(
  x: number, y: number, width: number, height: number, radius: number,
  orientation: "horizontal" | "vertical",
): string {
  if (orientation === "horizontal") {
    const r = Math.max(0, Math.min(radius, width, height / 2));
    if (width <= 0) return "";
    return [
      `M ${x} ${y}`,
      `H ${x + width - r}`,
      `Q ${x + width} ${y} ${x + width} ${y + r}`,
      `V ${y + height - r}`,
      `Q ${x + width} ${y + height} ${x + width - r} ${y + height}`,
      `H ${x}`,
      "Z",
    ].join(" ");
  }
  const r = Math.max(0, Math.min(radius, height, width / 2));
  if (height <= 0) return "";
  return [
    `M ${x} ${y + height}`,
    `V ${y + r}`,
    `Q ${x} ${y} ${x + r} ${y}`,
    `H ${x + width - r}`,
    `Q ${x + width} ${y} ${x + width} ${y + r}`,
    `V ${y + height}`,
    "Z",
  ].join(" ");
}

/** Clean axis ticks: 0 / 5 / 10 rather than 0 / 3.7 / 7.4. */
export function niceTicks(max: number, count = 4): number[] {
  if (max <= 0) return [0, 1];
  const rawStep = max / count;
  const magnitude = 10 ** Math.floor(Math.log10(rawStep));
  const normalised = rawStep / magnitude;
  const step =
    (normalised <= 1 ? 1 : normalised <= 2 ? 2 : normalised <= 5 ? 5 : 10) * magnitude;
  const ticks: number[] = [];
  for (let value = 0; value <= max + step * 0.5; value += step) {
    ticks.push(Math.round(value * 1000) / 1000);
  }
  return ticks;
}
