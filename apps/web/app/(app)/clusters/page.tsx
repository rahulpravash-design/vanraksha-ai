"use client";

/**
 * Cluster review.
 *
 * The review verdict is not administrative bookkeeping: it is the ground truth
 * that alert precision is measured against. Without it there is no way to tell
 * whether the detector is earning the field visits it costs, so it is given the
 * same weight on screen as the detection itself.
 */

import { useCallback, useEffect, useState } from "react";

import { ApiError, api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { syndromeLabel } from "@/lib/bands";
import { formatDate, relativeTime, titleCase } from "@/lib/format";
import { Button, Card, EmptyState, Notice, Spinner } from "@/components/ui";
import type { Cluster } from "@/lib/types";

const OUTCOMES = [
  { key: "confirmed", label: "Confirm", tone: "var(--status-critical)",
    help: "A real event. Keeps it on the map and counts as a true positive." },
  { key: "under_investigation", label: "Investigating", tone: "var(--status-warning)",
    help: "Assigned for a field visit; verdict pending." },
  { key: "dismissed", label: "Dismiss", tone: "var(--text-muted)",
    help: "Not a real event. Counts against alert precision and stops it being re-raised." },
] as const;

export default function ClustersPage() {
  const { hasRole } = useAuth();
  const [clusters, setClusters] = useState<Cluster[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [sweeping, setSweeping] = useState(false);

  const canSweep = hasRole("block_admin", "district_admin", "super_admin");

  const load = useCallback(() => {
    api
      .listClusters({ days: 60 })
      .then(setClusters)
      .catch((cause) =>
        setError(cause instanceof ApiError ? cause.message : "Could not load clusters."),
      );
  }, []);

  useEffect(load, [load]);

  async function sweep() {
    setSweeping(true);
    try {
      await api.runSweep(21);
      load();
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "The sweep failed.");
    } finally {
      setSweeping(false);
    }
  }

  if (error) return <Notice tone="warning" title={error} />;
  if (!clusters) return <Spinner label="Loading clusters" />;

  const live = clusters.filter((c) => c.status === "active" || c.status === "under_investigation");
  const settled = clusters.filter((c) => !live.includes(c));

  return (
    <div className="space-y-5">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">Clusters</h1>
          <p className="mt-1 text-sm text-ink-secondary">
            Reports close in distance, close in time, and similar in presentation.
          </p>
        </div>
        {canSweep ? (
          <Button variant="secondary" onClick={sweep} disabled={sweeping}>
            {sweeping ? "Running…" : "Run detection now"}
          </Button>
        ) : null}
      </header>

      {live.length === 0 ? (
        <Card>
          <EmptyState
            title="No active clusters"
            body="Reports are not grouping into anything unusual. A cluster needs at least three related reports within a few kilometres and a few days of each other."
          />
        </Card>
      ) : (
        <ul className="space-y-4">
          {live.map((cluster) => (
            <ClusterCard key={cluster.id} cluster={cluster} onReviewed={load} />
          ))}
        </ul>
      )}

      {settled.length > 0 ? (
        <section>
          <h2 className="mb-3 text-sm font-semibold text-ink">Settled</h2>
          <ul className="space-y-3">
            {settled.map((cluster) => (
              <li key={cluster.id}>
                <Card>
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div>
                      <p className="text-sm font-medium text-ink">
                        {syndromeLabel(cluster.dominant_syndrome)} &middot;{" "}
                        {cluster.report_count} reports
                      </p>
                      <p className="mt-0.5 text-xs text-ink-muted">
                        {cluster.villages.join(", ") || "Unnamed locality"} &middot;{" "}
                        {formatDate(cluster.first_seen)}
                      </p>
                    </div>
                    <span className="text-xs text-ink-secondary">
                      {titleCase(cluster.status)}
                    </span>
                  </div>
                  {cluster.review_notes ? (
                    <p className="mt-3 text-xs italic text-ink-muted">
                      &ldquo;{cluster.review_notes}&rdquo;
                    </p>
                  ) : null}
                </Card>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </div>
  );
}

function ClusterCard({ cluster, onReviewed }: { cluster: Cluster; onReviewed: () => void }) {
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function review(outcome: string) {
    setBusy(true);
    setError(null);
    try {
      await api.reviewCluster(cluster.id, outcome, notes);
      onReviewed();
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "Could not record the review.");
    } finally {
      setBusy(false);
    }
  }

  const accelerating = cluster.growth_ratio > 1.3;

  return (
    <li>
      <Card>
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0">
            <h2 className="text-base font-semibold text-ink">
              {syndromeLabel(cluster.dominant_syndrome)} cluster
            </h2>
            <p className="mt-1 text-sm text-ink-secondary">
              {cluster.villages.join(", ") || "Unnamed locality"}
            </p>
          </div>
          <Severity value={cluster.severity_score} />
        </div>

        <p className="mt-4 text-sm leading-relaxed text-ink">{cluster.explanation}</p>

        <dl className="mt-4 grid grid-cols-2 gap-3 text-xs sm:grid-cols-4">
          <Metric label="Reports" value={String(cluster.report_count)} />
          <Metric label="Animals" value={String(cluster.animal_count)} />
          <Metric
            label="Deaths"
            value={String(cluster.death_count)}
            tone={cluster.death_count > 0 ? "critical" : undefined}
          />
          <Metric
            label="Trend"
            value={accelerating ? "Accelerating" : cluster.growth_ratio < 0.7 ? "Declining" : "Stable"}
            tone={accelerating ? "critical" : undefined}
          />
        </dl>

        <p className="mt-3 text-[11px] text-ink-muted">
          Spread across {cluster.radius_km.toFixed(1)} km &middot; first seen{" "}
          {relativeTime(cluster.first_seen)} &middot; detected by {cluster.detector_version}
        </p>

        {cluster.top_symptoms.length > 0 ? (
          <div className="mt-3 flex flex-wrap gap-1.5">
            {cluster.top_symptoms.map((symptom) => (
              <span
                key={symptom.code}
                className="rounded-full border px-2.5 py-0.5 text-[11px] text-ink-secondary"
                style={{ borderColor: "var(--border)" }}
              >
                {titleCase(symptom.code)} &middot; {symptom.count}
              </span>
            ))}
          </div>
        ) : null}

        <div className="mt-5 border-t pt-4" style={{ borderColor: "var(--border)" }}>
          <p className="text-xs font-medium text-ink">Reviewer verdict</p>
          <p className="mt-1 text-[11px] leading-relaxed text-ink-muted">
            This is what alert precision is measured against. Dismissing a false cluster is
            as useful to the system as confirming a real one.
          </p>
          <textarea
            value={notes}
            onChange={(event) => setNotes(event.target.value)}
            rows={2}
            placeholder="What did you find?"
            className="mt-3 w-full rounded-lg border bg-surface-2 px-3 py-2 text-xs text-ink"
            style={{ borderColor: "var(--border)" }}
          />
          {error ? <p className="mt-2 text-xs" style={{ color: "var(--status-critical)" }}>{error}</p> : null}
          <div className="mt-3 flex flex-wrap gap-2">
            {OUTCOMES.map((outcome) => (
              <button
                key={outcome.key}
                type="button"
                disabled={busy}
                onClick={() => review(outcome.key)}
                title={outcome.help}
                className="min-h-[40px] rounded-lg border px-3.5 text-xs font-medium disabled:opacity-50"
                style={{ borderColor: outcome.tone, color: outcome.tone }}
              >
                {outcome.label}
              </button>
            ))}
          </div>
        </div>
      </Card>
    </li>
  );
}

function Severity({ value }: { value: number }) {
  const tone =
    value >= 70 ? "var(--status-critical)" : value >= 45 ? "var(--status-serious)" : "var(--status-warning)";
  return (
    <div className="shrink-0 text-right">
      <p className="tabular text-2xl font-semibold leading-none" style={{ color: tone }}>
        {Math.round(value)}
      </p>
      <p className="mt-1 text-[11px] text-ink-muted">severity</p>
    </div>
  );
}

function Metric({ label, value, tone }: { label: string; value: string; tone?: "critical" }) {
  return (
    <div>
      <dt className="text-ink-muted">{label}</dt>
      <dd
        className="tabular mt-0.5 text-sm font-medium"
        style={{ color: tone === "critical" ? "var(--status-critical)" : "var(--text-primary)" }}
      >
        {value}
      </dd>
    </div>
  );
}
