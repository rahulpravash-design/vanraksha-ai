"use client";

/**
 * Vaccination coverage.
 *
 * Part-to-whole across three states, so a single segmented meter rather than a
 * pie. Segments are separated by a 2px gap in the surface colour -- no strokes
 * drawn around the marks. Each segment carries its label below rather than
 * inside, so nothing is ever clipped by a narrow segment.
 *
 * The three states are qualitatively different (protected, lapsed, never
 * recorded), which is what status colour is for; each is paired with a written
 * label so the colour never carries the meaning alone.
 */

import { ChartFrame } from "./ChartFrame";
import { formatPercent } from "@/lib/format";

export interface CoverageData {
  animals: number;
  covered: number;
  overdue: number;
  never: number;
  coverage_rate: number | null;
}

const SEGMENTS = [
  { key: "covered", label: "Up to date", colour: "var(--status-good)" },
  { key: "overdue", label: "Overdue", colour: "var(--status-warning)" },
  { key: "never", label: "None recorded", colour: "var(--text-muted)" },
] as const;

const WIDTH = 460;
const BAR_HEIGHT = 22;
const GAP = 2;

export function CoverageMeter({ data }: { data: CoverageData }) {
  const table = {
    columns: ["State", "Animals", "Share"],
    rows: SEGMENTS.map((segment) => [
      segment.label,
      data[segment.key],
      data.animals ? formatPercent(data[segment.key] / data.animals) : "--",
    ]),
  };

  if (!data.animals) {
    return (
      <ChartFrame title="Vaccination coverage" table={table}>
        <p className="py-10 text-center text-xs text-ink-muted">
          No animals are registered in this scope yet.
        </p>
      </ChartFrame>
    );
  }

  let cursor = 0;
  const pieces = SEGMENTS.map((segment) => {
    const value = data[segment.key];
    const width = (value / data.animals) * (WIDTH - GAP * 2);
    const piece = { ...segment, value, x: cursor, width };
    cursor += width + GAP;
    return piece;
  }).filter((piece) => piece.value > 0);

  return (
    <ChartFrame
      title="Vaccination coverage"
      subtitle={`${data.animals} animal${data.animals === 1 ? "" : "s"} in scope`}
      table={table}
      footer="Coverage counts animals whose most recent booster is not past its due date."
    >
      <p className="mb-3 text-3xl font-semibold leading-none text-ink">
        {formatPercent(data.coverage_rate)}
      </p>

      <svg
        viewBox={`0 0 ${WIDTH} ${BAR_HEIGHT}`}
        className="w-full"
        style={{ height: BAR_HEIGHT }}
        role="img"
        aria-label={pieces
          .map((p) => `${p.label}: ${p.value} of ${data.animals}`)
          .join(", ")}
      >
        {pieces.map((piece, index) => (
          <rect
            key={piece.key}
            x={piece.x}
            y={0}
            width={Math.max(piece.width, 2)}
            height={BAR_HEIGHT}
            rx={index === 0 || index === pieces.length - 1 ? 4 : 0}
            fill={piece.colour}
          >
            <title>{`${piece.label}: ${piece.value} of ${data.animals}`}</title>
          </rect>
        ))}
      </svg>

      <ul className="mt-3 flex flex-wrap gap-x-5 gap-y-1.5">
        {SEGMENTS.map((segment) => (
          <li key={segment.key} className="flex items-center gap-2 text-xs text-ink-secondary">
            <span
              aria-hidden="true"
              className="inline-block h-2.5 w-2.5 rounded-sm"
              style={{ background: segment.colour }}
            />
            {segment.label}
            <span className="tabular font-medium text-ink">{data[segment.key]}</span>
          </li>
        ))}
      </ul>
    </ChartFrame>
  );
}
