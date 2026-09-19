"use client";

/**
 * Reports by triage band.
 *
 * Bands are *ordered* (routine through emergency), so this uses the ordinal
 * ramp -- one hue stepped light to dark, with the step gaps wide enough that
 * adjacent levels stay distinguishable. Five unrelated categorical hues would
 * imply the bands are five unrelated things, and a value-ramp keyed to bar
 * length would double-encode what the bar already shows.
 */

import { useState } from "react";

import { BANDS, BAND_LABEL, BAND_RAMP, type Band } from "@/lib/bands";
import { ChartFrame, barPath, niceTicks } from "./ChartFrame";

const WIDTH = 460;
const ROW_HEIGHT = 34;
const BAR_HEIGHT = 20;
const LABEL_WIDTH = 96;
const VALUE_WIDTH = 44;
const TOP = 6;
const AXIS_BAND = 24;

export function BandDistribution({ counts }: { counts: Record<string, number> }) {
  const [hover, setHover] = useState<Band | null>(null);

  const data = BANDS.map((band) => ({ band, count: counts[band] ?? 0 }));
  const total = data.reduce((sum, row) => sum + row.count, 0);
  const max = Math.max(...data.map((row) => row.count), 1);
  const ticks = niceTicks(max, 3);
  const top = ticks[ticks.length - 1];

  const plotWidth = WIDTH - LABEL_WIDTH - VALUE_WIDTH;
  // The container has to include the axis band, or the card gets a nested scroll.
  const height = TOP + data.length * ROW_HEIGHT + AXIS_BAND;

  const table = {
    columns: ["Band", "Reports", "Share"],
    rows: data.map((row) => [
      BAND_LABEL[row.band],
      row.count,
      total ? `${Math.round((row.count / total) * 100)}%` : "--",
    ]),
  };

  if (total === 0) {
    return (
      <ChartFrame title="Reports by triage band" table={table}>
        <p className="py-10 text-center text-xs text-ink-muted">
          No reports were triaged in this period.
        </p>
      </ChartFrame>
    );
  }

  return (
    <ChartFrame
      title="Reports by triage band"
      subtitle={`${total} report${total === 1 ? "" : "s"} in this period`}
      table={table}
    >
      <svg
        viewBox={`0 0 ${WIDTH} ${height}`}
        className="w-full"
        style={{ height }}
        role="img"
        aria-label={data.map((r) => `${BAND_LABEL[r.band]}: ${r.count}`).join(", ")}
        onMouseLeave={() => setHover(null)}
      >
        {ticks.map((tick) => (
          <line
            key={tick}
            x1={LABEL_WIDTH + (tick / top) * plotWidth}
            x2={LABEL_WIDTH + (tick / top) * plotWidth}
            y1={TOP}
            y2={TOP + data.length * ROW_HEIGHT}
            stroke="var(--grid)"
            strokeWidth="1"
          />
        ))}

        {data.map((row, index) => {
          const y = TOP + index * ROW_HEIGHT + (ROW_HEIGHT - BAR_HEIGHT) / 2;
          const width = (row.count / top) * plotWidth;
          return (
            <g key={row.band} onMouseEnter={() => setHover(row.band)}>
              <rect
                x={0} y={TOP + index * ROW_HEIGHT} width={WIDTH} height={ROW_HEIGHT}
                fill={hover === row.band ? "var(--surface-2)" : "transparent"}
              />
              <text
                x={LABEL_WIDTH - 10} y={y + BAR_HEIGHT / 2 + 4}
                textAnchor="end" fontSize="11" fill="var(--text-secondary)"
              >
                {BAND_LABEL[row.band]}
              </text>
              {row.count > 0 ? (
                <path
                  d={barPath(LABEL_WIDTH, y, Math.max(width, 2), BAR_HEIGHT, 4, "horizontal")}
                  fill={BAND_RAMP[row.band]}
                />
              ) : null}
              {/* Value at the tip -- outside the bar, so it is never clipped. */}
              <text
                x={LABEL_WIDTH + Math.max(width, 2) + 8}
                y={y + BAR_HEIGHT / 2 + 4}
                fontSize="11" fontWeight="600" fill="var(--text-primary)" className="tabular"
              >
                {row.count}
              </text>
            </g>
          );
        })}

        <line
          x1={LABEL_WIDTH} x2={LABEL_WIDTH}
          y1={TOP} y2={TOP + data.length * ROW_HEIGHT}
          stroke="var(--axis)" strokeWidth="1"
        />

        {ticks.map((tick) => (
          <text
            key={`tick-${tick}`}
            x={LABEL_WIDTH + (tick / top) * plotWidth}
            y={TOP + data.length * ROW_HEIGHT + 16}
            textAnchor="middle" fontSize="10" fill="var(--text-muted)" className="tabular"
          >
            {tick}
          </text>
        ))}
      </svg>
    </ChartFrame>
  );
}
