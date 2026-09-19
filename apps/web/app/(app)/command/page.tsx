"use client";

import dynamic from "next/dynamic";
import { useEffect, useState } from "react";

import { api } from "@/lib/api";
import { syndromeLabel } from "@/lib/bands";
import { formatNumber } from "@/lib/format";
import { Card, CardHeader, Notice, Spinner, StatTile } from "@/components/ui";
import type { Cluster, ScopeSummary, VillageRow } from "@/lib/types";

// Three.js is a large bundle and touches `window` at module scope, so it is
// loaded on the client only and kept out of every other route's payload.
const CommandCenter = dynamic(
  () => import("@/components/three/CommandCenter").then((m) => m.CommandCenter),
  {
    ssr: false,
    loading: () => <Spinner label="Preparing the district view" />,
  },
);

export default function CommandPage() {
  const [villages, setVillages] = useState<VillageRow[] | null>(null);
  const [clusters, setClusters] = useState<Cluster[]>([]);
  const [summary, setSummary] = useState<ScopeSummary | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    Promise.all([
      api.villageRows(30),
      api.listClusters({ status: "active", days: 60 }).catch(() => [] as Cluster[]),
      api.summary(30),
    ])
      .then(([v, c, s]) => {
        if (cancelled) return;
        setVillages(v);
        setClusters(c);
        setSummary(s);
      })
      .catch(() => {
        if (!cancelled) setFailed(true);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (failed) return <Notice tone="warning" title="Could not load the district view." />;
  if (!villages || !summary) return <Spinner label="Loading the district" />;

  const reporting = villages.filter((v) => v.report_count > 0).length;

  return (
    <div className="space-y-5">
      <header>
        <h1 className="text-xl font-semibold tracking-tight">District command view</h1>
        <p className="mt-1 text-sm text-ink-secondary">
          Column height is reporting volume; colour marks whether a village holds an
          escalated case or a death.
        </p>
      </header>

      <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <StatTile
          label="Villages reporting"
          value={`${reporting} / ${villages.length}`}
          note="Silence is not the same as health"
        />
        <StatTile label="Reports" value={formatNumber(summary.report_count)} note="Last 30 days" />
        <StatTile
          label="Active clusters"
          value={formatNumber(clusters.length)}
          tone={clusters.length > 0 ? "critical" : "neutral"}
          note={clusters.length ? "Drawn as rings below" : "Nothing flagged"}
        />
        <StatTile
          label="Overdue cases"
          value={formatNumber(summary.overdue_cases)}
          tone={summary.overdue_cases > 0 ? "critical" : "neutral"}
          note="Past their response target"
        />
      </section>

      <Card padded={false}>
        <CommandCenter villages={villages} clusters={clusters} />
      </Card>

      {clusters.length > 0 ? (
        <Card>
          <CardHeader title="What the rings are" subtitle="Each is an event under review" />
          <ul className="space-y-3">
            {clusters.map((cluster) => (
              <li key={cluster.id} className="flex items-start justify-between gap-4">
                <div className="min-w-0">
                  <p className="text-sm font-medium text-ink">
                    {syndromeLabel(cluster.dominant_syndrome)} &middot;{" "}
                    {cluster.villages.join(", ") || "one locality"}
                  </p>
                  <p className="mt-0.5 text-xs leading-relaxed text-ink-secondary">
                    {cluster.explanation}
                  </p>
                </div>
                <span
                  className="tabular shrink-0 text-lg font-semibold"
                  style={{ color: "var(--status-critical)" }}
                >
                  {Math.round(cluster.severity_score)}
                </span>
              </li>
            ))}
          </ul>
        </Card>
      ) : null}
    </div>
  );
}
