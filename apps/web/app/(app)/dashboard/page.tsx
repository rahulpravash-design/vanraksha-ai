"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { formatNumber, formatPercent } from "@/lib/format";
import { syndromeLabel } from "@/lib/bands";
import { BandDistribution } from "@/components/charts/BandDistribution";
import { CoverageMeter } from "@/components/charts/CoverageMeter";
import { ReportTrend } from "@/components/charts/ReportTrend";
import { VillageBars } from "@/components/charts/VillageBars";
import { Card, CardHeader, Notice, Spinner, StatTile } from "@/components/ui";
import type { Alert, Coverage, Performance, ScopeSummary, VillageRow } from "@/lib/types";

export default function DashboardPage() {
  const { user, isStaff } = useAuth();
  const [summary, setSummary] = useState<ScopeSummary | null>(null);
  const [villages, setVillages] = useState<VillageRow[]>([]);
  const [coverage, setCoverage] = useState<Coverage | null>(null);
  const [performance, setPerformance] = useState<Performance | null>(null);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    Promise.all([
      api.summary(30),
      api.villageRows(30),
      api.coverage(),
      isStaff ? api.performance(90).catch(() => null) : Promise.resolve(null),
      api.listAlerts({ unacknowledged_only: true }).catch(() => [] as Alert[]),
    ])
      .then(([s, v, c, p, a]) => {
        if (cancelled) return;
        setSummary(s);
        setVillages(v);
        setCoverage(c);
        setPerformance(p);
        setAlerts(a);
      })
      .catch(() => {
        if (!cancelled) setFailed(true);
      });
    return () => {
      cancelled = true;
    };
  }, [isStaff]);

  if (failed) {
    return (
      <Notice tone="warning" title="Could not load the dashboard">
        The API did not respond. Check that it is running, then reload.
      </Notice>
    );
  }

  if (!summary) return <Spinner label="Loading your scope" />;

  const delta = summary.report_count - summary.previous_period_count;

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-xl font-semibold tracking-tight">{summary.scope}</h1>
        <p className="mt-1 text-sm text-ink-secondary">
          Last {summary.period_days} days &middot; signed in as {user?.full_name}
        </p>
      </header>

      {alerts.length > 0 ? (
        <section className="space-y-3">
          {alerts.slice(0, 3).map((alert) => (
            <Notice
              key={alert.id}
              tone={alert.severity >= 60 ? "critical" : "warning"}
              title={alert.title}
            >
              <p>{alert.body}</p>
              <p className="mt-1.5 text-ink-muted">{alert.scope}</p>
            </Notice>
          ))}
        </section>
      ) : null}

      <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <StatTile
          label="Reports filed"
          value={formatNumber(summary.report_count)}
          delta={
            summary.previous_period_count > 0
              ? {
                  text: `${Math.abs(delta)} vs previous period`,
                  direction: delta > 0 ? "up" : delta < 0 ? "down" : "flat",
                  // More reporting is a working system, not a worsening one.
                  good: delta >= 0,
                }
              : undefined
          }
          note={`${formatNumber(summary.animal_count)} animals covered`}
        />
        <StatTile
          label="Open cases"
          value={formatNumber(summary.open_cases)}
          note={
            summary.overdue_cases > 0
              ? `${summary.overdue_cases} past their response target`
              : "None past their response target"
          }
          tone={summary.overdue_cases > 0 ? "critical" : "neutral"}
        />
        <StatTile
          label="Active clusters"
          value={formatNumber(summary.active_clusters)}
          note={summary.active_clusters ? "Awaiting review or response" : "Nothing flagged"}
          tone={summary.active_clusters > 0 ? "critical" : "neutral"}
        />
        <StatTile
          label="Deaths recorded"
          value={formatNumber(summary.death_count)}
          note={`${formatNumber(summary.overdue_vaccinations)} vaccinations overdue`}
          tone={summary.death_count > 0 ? "critical" : "neutral"}
        />
      </section>

      <section className="grid gap-5 lg:grid-cols-2">
        <div className="lg:col-span-2">
          <ReportTrend
            points={summary.weekly_series}
            trend={summary.trend}
          />
        </div>
        <BandDistribution counts={summary.band_counts} />
        <VillageBars
          rows={villages.map((row) => ({
            name: row.name,
            report_count: row.report_count,
            escalated_count: row.escalated_count,
            death_count: row.death_count,
          }))}
        />
        {coverage ? <CoverageMeter data={coverage} /> : null}
        <PresentationMix counts={summary.syndrome_counts} />
      </section>

      {performance ? <PerformancePanel data={performance} /> : null}
    </div>
  );
}

/**
 * Which presentations are being reported.
 *
 * A list rather than a pie: these are close values across many categories,
 * which is exactly what a pie is worst at.
 */
function PresentationMix({ counts }: { counts: Record<string, number> }) {
  const rows = Object.entries(counts).sort((a, b) => b[1] - a[1]).slice(0, 6);
  const total = rows.reduce((sum, [, count]) => sum + count, 0);

  return (
    <Card>
      <CardHeader
        title="What is being reported"
        subtitle="Syndromic groups, not diagnoses"
      />
      {rows.length === 0 ? (
        <p className="py-8 text-center text-xs text-ink-muted">
          Nothing has been reported in this period.
        </p>
      ) : (
        <ul className="space-y-2.5">
          {rows.map(([syndrome, count]) => (
            <li key={syndrome} className="flex items-center gap-3">
              <span className="w-40 shrink-0 text-xs text-ink-secondary">
                {syndromeLabel(syndrome)}
              </span>
              <span className="h-2 flex-1 overflow-hidden rounded-full" style={{ background: "var(--surface-2)" }}>
                <span
                  className="block h-full rounded-full"
                  style={{
                    width: `${total ? (count / total) * 100 : 0}%`,
                    background: "var(--series-1)",
                  }}
                />
              </span>
              <span className="tabular w-8 shrink-0 text-right text-xs font-medium text-ink">
                {count}
              </span>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

/**
 * Operational KPIs.
 *
 * Nulls render as "not enough data" rather than zero: a median resolution time
 * of "no cases" is not zero hours, and printing zero on a dashboard someone
 * makes decisions from would be a lie.
 */
function PerformancePanel({ data }: { data: Performance }) {
  const metrics = [
    {
      label: "Report to server",
      value: data.median_reporting_lag_hours,
      unit: "h",
      note: "Median delay between observation and the record arriving",
    },
    {
      label: "Open to assigned",
      value: data.median_assignment_hours,
      unit: "h",
      note: "Median time a case waits before a vet is assigned",
    },
    {
      label: "Open to closed",
      value: data.median_resolution_hours,
      unit: "h",
      note: "Median time to a recorded outcome",
    },
  ];

  return (
    <Card>
      <CardHeader
        title="Response performance"
        subtitle={`Measured from recorded timestamps over ${data.period_days} days`}
      />
      <div className="grid gap-4 sm:grid-cols-3">
        {metrics.map((metric) => (
          <div key={metric.label}>
            <p className="text-xs text-ink-secondary">{metric.label}</p>
            <p className="tabular mt-1 text-2xl font-semibold text-ink">
              {metric.value === null ? (
                <span className="text-base font-normal text-ink-muted">Not enough data</span>
              ) : (
                <>
                  {metric.value.toFixed(1)}
                  <span className="ml-0.5 text-sm font-normal text-ink-muted">{metric.unit}</span>
                </>
              )}
            </p>
            <p className="mt-1 text-[11px] leading-relaxed text-ink-muted">{metric.note}</p>
          </div>
        ))}
      </div>
      <dl className="mt-5 grid gap-3 border-t pt-4 text-xs sm:grid-cols-3" style={{ borderColor: "var(--border)" }}>
        <div>
          <dt className="text-ink-muted">Met response target</dt>
          <dd className="tabular mt-0.5 font-medium text-ink">
            {data.sla_met_rate === null ? "Not enough data" : formatPercent(data.sla_met_rate)}
          </dd>
        </div>
        <div>
          <dt className="text-ink-muted">Filed offline</dt>
          <dd className="tabular mt-0.5 font-medium text-ink">
            {data.offline_share === null ? "--" : formatPercent(data.offline_share)}
          </dd>
        </div>
        <div>
          <dt className="text-ink-muted">Report completeness</dt>
          <dd className="tabular mt-0.5 font-medium text-ink">
            {data.data_completeness === null ? "--" : formatPercent(data.data_completeness)}
          </dd>
        </div>
      </dl>
    </Card>
  );
}
