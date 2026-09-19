"use client";

/**
 * Weekly reporting volume.
 *
 * One series, so there is no legend -- the title says what is plotted, and a
 * one-swatch legend would only restate it. The endpoint is direct-labelled; the
 * rest of the values live on the axis and in the hover tooltip, because a number
 * beside every point is chaos that goes unread.
 */

import { useId, useState } from "react";

import { ChartFrame, niceTicks } from "./ChartFrame";

export interface TrendPoint {
  period_start: string;
  count: number;
}

const WIDTH = 640;
const HEIGHT = 200;
const PADDING = { top: 16, right: 52, bottom: 30, left: 36 };

export function ReportTrend({
  points, trend,
}: {
  points: TrendPoint[];
  trend?: string;
}) {
  const gradientId = useId();
  const [hover, setHover] = useState<number | null>(null);

  const table = {
    columns: ["Week starting", "Reports"],
    rows: points.map((p) => [formatWeek(p.period_start), p.count]),
  };

  if (points.length < 2) {
    return (
      <ChartFrame
        title="Weekly reporting volume"
        subtitle="Not enough history to draw a trend"
        table={table}
      >
        <p className="py-10 text-center text-xs text-ink-muted">
          At least two weeks of reporting are needed before a trend means anything.
        </p>
      </ChartFrame>
    );
  }

  const maxCount = Math.max(...points.map((p) => p.count), 1);
  const ticks = niceTicks(maxCount);
  const top = ticks[ticks.length - 1];

  const plotWidth = WIDTH - PADDING.left - PADDING.right;
  const plotHeight = HEIGHT - PADDING.top - PADDING.bottom;

  const x = (index: number) =>
    PADDING.left + (index / (points.length - 1)) * plotWidth;
  const y = (value: number) =>
    PADDING.top + plotHeight - (value / top) * plotHeight;

  const line = points.map((p, i) => `${i === 0 ? "M" : "L"} ${x(i)} ${y(p.count)}`).join(" ");
  const area =
    `${line} L ${x(points.length - 1)} ${PADDING.top + plotHeight} ` +
    `L ${x(0)} ${PADDING.top + plotHeight} Z`;

  const last = points[points.length - 1];
  const active = hover === null ? null : points[hover];

  return (
    <ChartFrame
      title="Weekly reporting volume"
      subtitle={trend ? `Reporting is ${trend}` : undefined}
      table={table}
      footer="A quiet week is not the same as a healthy week — it can also mean nobody was able to report."
    >
      <div className="relative">
        <svg
          viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
          className="w-full"
          style={{ height: HEIGHT }}
          role="img"
          aria-label={`Weekly report counts over ${points.length} weeks, ending at ${last.count}.`}
          onMouseLeave={() => setHover(null)}
        >
          <defs>
            <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="var(--series-1)" stopOpacity="0.16" />
              <stop offset="100%" stopColor="var(--series-1)" stopOpacity="0.01" />
            </linearGradient>
          </defs>

          {/* Recessive, solid hairline grid -- never dashed. */}
          {ticks.map((tick) => (
            <g key={tick}>
              <line
                x1={PADDING.left} x2={WIDTH - PADDING.right}
                y1={y(tick)} y2={y(tick)}
                stroke="var(--grid)" strokeWidth="1"
              />
              <text
                x={PADDING.left - 8} y={y(tick) + 3}
                textAnchor="end" fontSize="10" fill="var(--text-muted)"
                className="tabular"
              >
                {tick}
              </text>
            </g>
          ))}

          <path d={area} fill={`url(#${gradientId})`} />
          <path
            d={line} fill="none" stroke="var(--series-1)" strokeWidth="2"
            strokeLinejoin="round" strokeLinecap="round"
          />

          {/* Endpoint marker, with a surface ring so it stays legible. */}
          <circle
            cx={x(points.length - 1)} cy={y(last.count)} r="4.5"
            fill="var(--series-1)" stroke="var(--surface-1)" strokeWidth="2"
          />
          <text
            x={x(points.length - 1) + 10} y={y(last.count) + 4}
            fontSize="11" fontWeight="600" fill="var(--text-primary)" className="tabular"
          >
            {last.count}
          </text>

          {active ? (
            <>
              <line
                x1={x(hover as number)} x2={x(hover as number)}
                y1={PADDING.top} y2={PADDING.top + plotHeight}
                stroke="var(--axis)" strokeWidth="1"
              />
              <circle
                cx={x(hover as number)} cy={y(active.count)} r="4.5"
                fill="var(--series-1)" stroke="var(--surface-1)" strokeWidth="2"
              />
            </>
          ) : null}

          <line
            x1={PADDING.left} x2={WIDTH - PADDING.right}
            y1={PADDING.top + plotHeight} y2={PADDING.top + plotHeight}
            stroke="var(--axis)" strokeWidth="1"
          />

          {points.map((point, index) =>
            index % Math.ceil(points.length / 6) === 0 || index === points.length - 1 ? (
              <text
                key={point.period_start}
                x={x(index)} y={HEIGHT - 10}
                textAnchor="middle" fontSize="10" fill="var(--text-muted)"
              >
                {formatWeek(point.period_start)}
              </text>
            ) : null,
          )}

          {/* Hit targets wider than the marks. */}
          {points.map((point, index) => (
            <rect
              key={`hit-${point.period_start}`}
              x={x(index) - plotWidth / (points.length - 1) / 2}
              y={PADDING.top}
              width={plotWidth / (points.length - 1)}
              height={plotHeight}
              fill="transparent"
              onMouseEnter={() => setHover(index)}
            />
          ))}
        </svg>

        {active ? (
          <div
            className="pointer-events-none absolute -translate-x-1/2 rounded-md border px-2 py-1 text-[11px] shadow-sm"
            style={{
              left: `${(x(hover as number) / WIDTH) * 100}%`,
              top: 0,
              borderColor: "var(--border)",
              background: "var(--surface-1)",
              color: "var(--text-primary)",
            }}
          >
            <span className="text-ink-muted">{formatWeek(active.period_start)}</span>{" "}
            <span className="tabular font-semibold">{active.count}</span>
          </div>
        ) : null}
      </div>
    </ChartFrame>
  );
}

function formatWeek(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleDateString("en-IN", { day: "numeric", month: "short" });
}
