"use client";

/**
 * Geographic view of reporting and clusters.
 *
 * Rendered as projected SVG rather than raster tiles, on purpose. A tile layer
 * needs a network round trip and usually an API key -- both of which are absent
 * in exactly the setting this platform is built for. Projecting the coordinates
 * directly means the map draws from data already in hand, works offline, and
 * carries no third-party dependency.
 *
 * Circle *area* encodes report count, not radius. Scaling the radius linearly
 * would make a village with four times the reports look sixteen times worse.
 */

import { useMemo, useState } from "react";

import { syndromeLabel } from "@/lib/bands";
import type { Cluster, VillageRow } from "@/lib/types";

const WIDTH = 720;
const HEIGHT = 440;
const MARGIN = 56;

interface Projection {
  x: (lon: number) => number;
  y: (lat: number) => number;
  kmToPx: number;
}

/**
 * Equirectangular projection with a latitude correction, fitted to the data.
 *
 * Adequate and honest at district scale: longitude degrees are narrowed by
 * cos(latitude) so shapes and distances do not stretch east-west.
 */
function buildProjection(points: { latitude: number; longitude: number }[]): Projection | null {
  if (!points.length) return null;

  const lats = points.map((p) => p.latitude);
  const lons = points.map((p) => p.longitude);
  const midLat = (Math.min(...lats) + Math.max(...lats)) / 2;
  const cos = Math.cos((midLat * Math.PI) / 180);

  // Work in a flat space where one unit is comparable in both directions.
  const flatX = lons.map((lon) => lon * cos);
  const minX = Math.min(...flatX);
  const maxX = Math.max(...flatX);
  const minY = Math.min(...lats);
  const maxY = Math.max(...lats);

  // A single point, or a perfectly collinear set, still needs a sane extent.
  const spanX = Math.max(maxX - minX, 0.02);
  const spanY = Math.max(maxY - minY, 0.02);

  const usableWidth = WIDTH - MARGIN * 2;
  const usableHeight = HEIGHT - MARGIN * 2;
  // One scale for both axes, so the map is never stretched to fill the box.
  const scale = Math.min(usableWidth / spanX, usableHeight / spanY);

  const offsetX = MARGIN + (usableWidth - spanX * scale) / 2;
  const offsetY = MARGIN + (usableHeight - spanY * scale) / 2;

  return {
    x: (lon: number) => offsetX + (lon * cos - minX) * scale,
    // SVG y grows downward; latitude grows north.
    y: (lat: number) => offsetY + (maxY - lat) * scale,
    kmToPx: scale / 111.32,
  };
}

export function VillageMap({
  villages, clusters, onSelect,
}: {
  villages: VillageRow[];
  clusters: Cluster[];
  onSelect?: (villageId: string) => void;
}) {
  const [hover, setHover] = useState<string | null>(null);

  const projection = useMemo(() => buildProjection(villages), [villages]);
  const maxReports = Math.max(...villages.map((v) => v.report_count), 1);

  if (!projection || !villages.length) {
    return (
      <div className="flex h-64 items-center justify-center text-xs text-ink-muted">
        No villages in scope to map.
      </div>
    );
  }

  // Area-proportional radius, with a floor so a village that reported once is
  // still visible and clickable.
  const radiusFor = (count: number) =>
    count === 0 ? 4 : 6 + 20 * Math.sqrt(count / maxReports);

  const hovered = villages.find((v) => v.village_id === hover) ?? null;

  return (
    <div className="relative">
      <svg
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        className="w-full"
        style={{ height: "auto", aspectRatio: `${WIDTH} / ${HEIGHT}` }}
        role="img"
        aria-label={`Map of ${villages.length} villages with ${clusters.length} active clusters.`}
        onMouseLeave={() => setHover(null)}
      >
        <rect width={WIDTH} height={HEIGHT} fill="var(--surface-2)" rx="12" />

        {/* A faint graticule for orientation; solid hairlines, never dashed. */}
        {Array.from({ length: 7 }, (_, i) => (
          <g key={i} opacity="0.5">
            <line
              x1={(WIDTH / 7) * i} x2={(WIDTH / 7) * i} y1={0} y2={HEIGHT}
              stroke="var(--grid)" strokeWidth="1"
            />
            <line
              x1={0} x2={WIDTH} y1={(HEIGHT / 7) * i} y2={(HEIGHT / 7) * i}
              stroke="var(--grid)" strokeWidth="1"
            />
          </g>
        ))}

        {/* Cluster extents sit under the villages so they never obscure them. */}
        {clusters.map((cluster) => {
          const cx = projection.x(cluster.centroid_lon);
          const cy = projection.y(cluster.centroid_lat);
          const r = Math.max(cluster.radius_km * projection.kmToPx, 26);
          return (
            <g key={cluster.id}>
              <circle
                cx={cx} cy={cy} r={r}
                fill="var(--status-critical)" fillOpacity="0.08"
                stroke="var(--status-critical)" strokeWidth="1.5" strokeOpacity="0.5"
              />
              <circle
                cx={cx} cy={cy} r={r}
                fill="none" stroke="var(--status-critical)" strokeWidth="1.5"
                style={{
                  transformOrigin: `${cx}px ${cy}px`,
                  animation: "pulse-ring 2.6s ease-out infinite",
                }}
              />
            </g>
          );
        })}

        {villages.map((village) => {
          const cx = projection.x(village.longitude);
          const cy = projection.y(village.latitude);
          const r = radiusFor(village.report_count);
          const isHovered = hover === village.village_id;

          return (
            <g
              key={village.village_id}
              onMouseEnter={() => setHover(village.village_id)}
              onClick={() => onSelect?.(village.village_id)}
              style={{ cursor: onSelect ? "pointer" : "default" }}
            >
              {/* Hit target larger than the mark. */}
              <circle cx={cx} cy={cy} r={Math.max(r + 8, 18)} fill="transparent" />
              <circle
                cx={cx} cy={cy} r={r}
                fill="var(--series-1)"
                fillOpacity={village.report_count ? 0.28 : 0.12}
                stroke="var(--series-1)"
                strokeWidth={isHovered ? 2.5 : 1.5}
              />
              {village.escalated_count > 0 ? (
                <circle
                  cx={cx} cy={cy} r={Math.max(4, r * 0.34)}
                  fill="var(--status-critical)"
                  stroke="var(--surface-2)" strokeWidth="2"
                />
              ) : null}
              <text
                x={cx} y={cy + r + 13}
                textAnchor="middle" fontSize="10"
                fill={isHovered ? "var(--text-primary)" : "var(--text-muted)"}
              >
                {village.name}
              </text>
            </g>
          );
        })}
      </svg>

      <div className="mt-3 flex flex-wrap items-center gap-x-5 gap-y-2 text-[11px] text-ink-secondary">
        <span className="flex items-center gap-1.5">
          <span
            aria-hidden="true"
            className="inline-block h-3 w-3 rounded-full"
            style={{ background: "color-mix(in srgb, var(--series-1) 28%, transparent)", border: "1.5px solid var(--series-1)" }}
          />
          Circle area is reports filed
        </span>
        <span className="flex items-center gap-1.5">
          <span
            aria-hidden="true"
            className="inline-block h-2 w-2 rounded-full"
            style={{ background: "var(--status-critical)" }}
          />
          Contains a case at priority or above
        </span>
        <span className="flex items-center gap-1.5">
          <span
            aria-hidden="true"
            className="inline-block h-3 w-3 rounded-full"
            style={{ border: "1.5px solid var(--status-critical)" }}
          />
          Active cluster extent
        </span>
      </div>

      {hovered ? (
        <div
          className="pointer-events-none absolute left-3 top-3 rounded-lg border px-3 py-2 text-[11px] shadow-sm"
          style={{ borderColor: "var(--border)", background: "var(--surface-1)" }}
        >
          <p className="text-xs font-semibold text-ink">{hovered.name}</p>
          <p className="mt-0.5 text-ink-muted">{hovered.block} block</p>
          <dl className="tabular mt-1.5 space-y-0.5 text-ink-secondary">
            <div className="flex gap-3">
              <dt className="w-20">Reports</dt>
              <dd className="font-medium text-ink">{hovered.report_count}</dd>
            </div>
            <div className="flex gap-3">
              <dt className="w-20">Escalated</dt>
              <dd className="font-medium text-ink">{hovered.escalated_count}</dd>
            </div>
            <div className="flex gap-3">
              <dt className="w-20">Deaths</dt>
              <dd className="font-medium text-ink">{hovered.death_count}</dd>
            </div>
          </dl>
        </div>
      ) : null}
    </div>
  );
}

export function ClusterLegend({ clusters }: { clusters: Cluster[] }) {
  if (!clusters.length) return null;
  return (
    <ul className="space-y-2">
      {clusters.map((cluster) => (
        <li key={cluster.id} className="flex items-start gap-2.5 text-xs">
          <span
            aria-hidden="true"
            className="mt-1 inline-block h-2 w-2 shrink-0 rounded-full"
            style={{ background: "var(--status-critical)" }}
          />
          <span>
            <span className="font-medium text-ink">
              {syndromeLabel(cluster.dominant_syndrome)}
            </span>
            <span className="text-ink-secondary">
              {" "}&middot; {cluster.report_count} reports in{" "}
              {cluster.villages.join(", ") || "one locality"}
            </span>
          </span>
        </li>
      ))}
    </ul>
  );
}
