"use client";

import { useEffect, useState } from "react";

import { api } from "@/lib/api";
import { ClusterLegend, VillageMap } from "@/components/map/VillageMap";
import { Card, CardHeader, Notice, Spinner } from "@/components/ui";
import type { Cluster, VillageRow } from "@/lib/types";

export default function MapPage() {
  const [villages, setVillages] = useState<VillageRow[] | null>(null);
  const [clusters, setClusters] = useState<Cluster[]>([]);
  const [days, setDays] = useState(30);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    Promise.all([
      api.villageRows(days),
      api.listClusters({ status: "active", days: 60 }).catch(() => [] as Cluster[]),
    ])
      .then(([v, c]) => {
        if (cancelled) return;
        setVillages(v);
        setClusters(c);
      })
      .catch(() => {
        if (!cancelled) setFailed(true);
      });
    return () => {
      cancelled = true;
    };
  }, [days]);

  if (failed) return <Notice tone="warning" title="Could not load the map data." />;
  if (!villages) return <Spinner label="Loading the map" />;

  return (
    <div className="space-y-5">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">Where reporting is happening</h1>
          <p className="mt-1 text-sm text-ink-secondary">
            Villages sized by reporting volume, with any active cluster drawn over them.
          </p>
        </div>
        <div className="flex gap-1">
          {[7, 30, 90].map((option) => (
            <button
              key={option}
              type="button"
              onClick={() => setDays(option)}
              aria-pressed={days === option}
              className="rounded-lg border px-3 py-1.5 text-xs"
              style={{
                borderColor: days === option ? "var(--series-1)" : "var(--border)",
                color: days === option ? "var(--series-1)" : "var(--text-secondary)",
                fontWeight: days === option ? 600 : 400,
              }}
            >
              {option} days
            </button>
          ))}
        </div>
      </header>

      <Card>
        <VillageMap villages={villages} clusters={clusters} />
      </Card>

      {clusters.length > 0 ? (
        <Card>
          <CardHeader
            title="Active clusters on this map"
            subtitle="Each ring is an event, not a single sick animal"
          />
          <ClusterLegend clusters={clusters} />
        </Card>
      ) : null}
    </div>
  );
}
