"use client";

/**
 * Reporting by village.
 *
 * Villages have no natural order, so every bar is one colour -- the single
 * series hue. Colouring them darker-where-bigger would spend the only free
 * channel restating the bar length.
 *
 * Deaths are shown as a separate marker rather than a second stacked series,
 * because they are a different measure at a very different scale and stacking
 * them would misrepresent both.
 */

import { useState } from "react";

import { ChartFrame, barPath, niceTicks } from "./ChartFrame";

export interface VillageBarRow {
  name: string;
  report_count: number;
  escalated_count: number;
  death_count: number;
}

const WIDTH = 460;
const ROW_HEIGHT = 30;
const BAR_HEIGHT = 18;
const LABEL_WIDTH = 108;
const VALUE_WIDTH = 46;
const TOP = 6;
const AXIS_BAND = 24;

export function VillageBars({ rows, limit = 8 }: { rows: VillageBarRow[]; limit?: number }) {
  const [hover, setHover] = useState<string | null>(null);

  const ranked = [...rows]
    .sort((a, b) => b.report_count - a.report_count)
    .slice(0, limit)
    .filter((row) => row.report_count > 0);

  const table = {
    columns: ["Village", "Reports", "Escalated", "Deaths"],
    rows: ranked.map((r) => [r.name, r.report_count, r.escalated_count, r.death_count]),
  };

  if (!ranked.length) {
    return (
      <ChartFrame title="Reporting by village" table={table}>
        <p className="py-10 text-center text-xs text-ink-muted">
          No village in this scope filed a report in the period.
        </p>
      </ChartFrame>
    );
  }

  const max = Math.max(...ranked.map((r) => r.report_count), 1);
  const ticks = niceTicks(max, 3);
  const top = ticks[ticks.length - 1];
  const plotWidth = WIDTH - LABEL_WIDTH - VALUE_WIDTH;
  const height = TOP + ranked.length * ROW_HEIGHT + AXIS_BAND;

  return (
    <ChartFrame
      title="Reporting by village"
      subtitle="Bar length is reports filed; a dot marks recorded deaths"
      table={table}
    >
      <svg
        viewBox={`0 0 ${WIDTH} ${height}`}
        className="w-full"
        style={{ height }}
        role="img"
        aria-label={ranked.map((r) => `${r.name}: ${r.report_count} reports`).join(", ")}
        onMouseLeave={() => setHover(null)}
      >
        {ticks.map((tick) => (
          <line
            key={tick}
            x1={LABEL_WIDTH + (tick / top) * plotWidth}
            x2={LABEL_WIDTH + (tick / top) * plotWidth}
            y1={TOP} y2={TOP + ranked.length * ROW_HEIGHT}
            stroke="var(--grid)" strokeWidth="1"
          />
        ))}

        {ranked.map((row, index) => {
          const y = TOP + index * ROW_HEIGHT + (ROW_HEIGHT - BAR_HEIGHT) / 2;
          const width = Math.max((row.report_count / top) * plotWidth, 2);
          return (
            <g key={row.name} onMouseEnter={() => setHover(row.name)}>
              <rect
                x={0} y={TOP + index * ROW_HEIGHT} width={WIDTH} height={ROW_HEIGHT}
                fill={hover === row.name ? "var(--surface-2)" : "transparent"}
              />
              <text
                x={LABEL_WIDTH - 10} y={y + BAR_HEIGHT / 2 + 4}
                textAnchor="end" fontSize="11" fill="var(--text-secondary)"
              >
                {truncate(row.name, 14)}
              </text>
              <path
                d={barPath(LABEL_WIDTH, y, width, BAR_HEIGHT, 4, "horizontal")}
                fill="var(--series-1)"
              />
              {row.death_count > 0 ? (
                <circle
                  cx={LABEL_WIDTH + width + 12} cy={y + BAR_HEIGHT / 2} r="4"
                  fill="var(--status-critical)" stroke="var(--surface-1)" strokeWidth="2"
                >
                  <title>{`${row.death_count} death(s) recorded in ${row.name}`}</title>
                </circle>
              ) : null}
              <text
                x={LABEL_WIDTH + width + (row.death_count > 0 ? 22 : 8)}
                y={y + BAR_HEIGHT / 2 + 4}
                fontSize="11" fontWeight="600" fill="var(--text-primary)" className="tabular"
              >
                {row.report_count}
              </text>
            </g>
          );
        })}

        <line
          x1={LABEL_WIDTH} x2={LABEL_WIDTH}
          y1={TOP} y2={TOP + ranked.length * ROW_HEIGHT}
          stroke="var(--axis)" strokeWidth="1"
        />
        {ticks.map((tick) => (
          <text
            key={`tick-${tick}`}
            x={LABEL_WIDTH + (tick / top) * plotWidth}
            y={TOP + ranked.length * ROW_HEIGHT + 16}
            textAnchor="middle" fontSize="10" fill="var(--text-muted)" className="tabular"
          >
            {tick}
          </text>
        ))}
      </svg>
    </ChartFrame>
  );
}

function truncate(value: string, max: number): string {
  return value.length > max ? `${value.slice(0, max - 1)}…` : value;
}
