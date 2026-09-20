"use client";

/**
 * The veterinary work queue.
 *
 * Ordering is the product. The API returns cases sorted by band and then by
 * time remaining against the response target, and this screen preserves that
 * order rather than re-sorting by anything the reader finds more familiar.
 */

import { useCallback, useEffect, useState } from "react";

import { ApiError, api } from "@/lib/api";
import { formatDateTime, hoursUntil, relativeTime } from "@/lib/format";
import { explanationRows, isBandFloor } from "@/lib/bands";
import { BandBadge, Button, Card, EmptyState, Notice, Spinner } from "@/components/ui";
import type { Case, HealthReport } from "@/lib/types";

export default function QueuePage() {
  const [cases, setCases] = useState<Case[] | null>(null);
  const [mineOnly, setMineOnly] = useState(false);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    api
      .caseQueue({ mine_only: mineOnly })
      .then(setCases)
      .catch((cause) =>
        setError(cause instanceof ApiError ? cause.message : "Could not load the queue."),
      );
  }, [mineOnly]);

  useEffect(load, [load]);

  if (error) return <Notice tone="warning" title={error} />;
  if (!cases) return <Spinner label="Loading the queue" />;

  return (
    <div className="space-y-5">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">Case queue</h1>
          <p className="mt-1 text-sm text-ink-secondary">
            Most urgent first, then by how close each case is to its response target.
          </p>
        </div>
        <label className="flex items-center gap-2 text-xs text-ink-secondary">
          <input
            type="checkbox"
            checked={mineOnly}
            onChange={(event) => setMineOnly(event.target.checked)}
            className="h-4 w-4"
          />
          Only cases assigned to me
        </label>
      </header>

      {cases.length === 0 ? (
        <Card>
          <EmptyState
            title="Nothing waiting"
            body={
              mineOnly
                ? "No cases are currently assigned to you."
                : "No open cases in your area. New reports scored at priority or above will appear here automatically."
            }
          />
        </Card>
      ) : (
        <ul className="space-y-3">
          {cases.map((item) => (
            <CaseRow
              key={item.id}
              item={item}
              expanded={expanded === item.id}
              onToggle={() => setExpanded(expanded === item.id ? null : item.id)}
              onChanged={load}
            />
          ))}
        </ul>
      )}
    </div>
  );
}

function CaseRow({
  item, expanded, onToggle, onChanged,
}: {
  item: Case;
  expanded: boolean;
  onToggle: () => void;
  onChanged: () => void;
}) {
  const [report, setReport] = useState<HealthReport | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!expanded || report) return;
    api.getReport(item.report_id).then(setReport).catch(() => setReport(null));
  }, [expanded, report, item.report_id]);

  const remaining = hoursUntil(item.due_at);
  const urgentDeadline = remaining !== null && remaining < 6;

  async function advance(status: string, outcome?: string) {
    setBusy(true);
    setError(null);
    try {
      await api.updateCase(item.id, { status, outcome });
      onChanged();
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "Could not update the case.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <li>
      <Card padded={false}>
        <button
          type="button"
          onClick={onToggle}
          aria-expanded={expanded}
          className="flex w-full items-start gap-4 p-4 text-left"
        >
          <BandBadge band={item.band} />

          <div className="min-w-0 flex-1">
            <p className="text-sm font-medium text-ink">
              {item.status === "open" ? "Unassigned" : titleise(item.status)}
              {item.cluster_id ? (
                <span
                  className="ml-2 rounded-full px-2 py-0.5 text-[10px]"
                  style={{
                    background: "color-mix(in srgb, var(--status-critical) 14%, transparent)",
                    color: "var(--status-critical)",
                  }}
                >
                  part of a cluster
                </span>
              ) : null}
            </p>
            <p className="mt-0.5 text-xs text-ink-muted">
              Opened {relativeTime(item.opened_at)}
            </p>
          </div>

          <div className="shrink-0 text-right">
            {item.is_overdue ? (
              <p className="text-xs font-medium" style={{ color: "var(--status-critical)" }}>
                Overdue
              </p>
            ) : item.due_at ? (
              <p
                className="text-xs"
                style={{ color: urgentDeadline ? "var(--status-critical)" : "var(--text-muted)" }}
              >
                Due {relativeTime(item.due_at)}
              </p>
            ) : null}
            <p className="mt-0.5 text-[11px] text-ink-muted">{expanded ? "Hide" : "Open"}</p>
          </div>
        </button>

        {expanded ? (
          <div className="border-t p-4" style={{ borderColor: "var(--border)" }}>
            {report === null ? (
              <Spinner label="Loading the report" />
            ) : (
              <div className="space-y-4">
                <div className="grid gap-3 text-xs sm:grid-cols-2">
                  <Detail label="Species" value={report.species} />
                  <Detail label="Reported" value={formatDateTime(report.reported_at)} />
                  <Detail
                    label="Signs"
                    value={report.symptom_codes.map(titleise).join(", ") || "None recorded"}
                  />
                  <Detail
                    label="Affected"
                    value={`${report.affected_count} animal(s)${report.deaths_count ? `, ${report.deaths_count} died` : ""}`}
                  />
                  {report.temperature_c ? (
                    <Detail label="Temperature" value={`${report.temperature_c} °C`} />
                  ) : null}
                  {report.submitted_offline ? (
                    <Detail label="Submission" value="Queued offline, synced later" />
                  ) : null}
                </div>

                {report.symptoms_text ? (
                  <p className="rounded-lg p-3 text-xs italic text-ink-secondary" style={{ background: "var(--surface-2)" }}>
                    &ldquo;{report.symptoms_text}&rdquo;
                  </p>
                ) : null}

                {report.assessment ? (
                  <>
                    <p className="text-sm leading-relaxed text-ink">
                      {report.assessment.recommended_action}
                    </p>

                    {report.assessment.cautions.map((caution) => (
                      <Notice key={caution.caution_id} tone="critical" title={caution.title}>
                        <ul className="space-y-1">
                          {caution.actions.map((action) => (
                            <li key={action}>&middot; {action}</li>
                          ))}
                        </ul>
                      </Notice>
                    ))}

                    <details className="text-xs">
                      <summary className="cursor-pointer text-ink-secondary">
                        Why it scored {Math.round(report.assessment.score)}
                      </summary>
                      <ul className="mt-2 space-y-1.5">
                        {explanationRows(report.assessment.contributions)
                          .map((c) => (
                            <li key={c.rule_id} className="flex gap-2.5">
                              <span
                                className="tabular w-10 shrink-0 text-right font-medium"
                                style={{
                                  color: isBandFloor(c)
                                    ? "var(--status-critical)"
                                    : "var(--text-primary)",
                                }}
                              >
                                {isBandFloor(c) ? "Floor" : `${c.points > 0 ? "+" : ""}${c.points}`}
                              </span>
                              <span className="text-ink-secondary">{c.evidence}</span>
                            </li>
                          ))}
                      </ul>
                    </details>
                  </>
                ) : null}

                {error ? <Notice tone="critical" title={error} /> : null}

                {item.status !== "closed" && item.status !== "resolved" ? (
                  <div className="flex flex-wrap gap-2">
                    {item.status === "open" || item.status === "assigned" ? (
                      <Button
                        variant="secondary"
                        disabled={busy}
                        onClick={() => advance("in_progress")}
                      >
                        Start work
                      </Button>
                    ) : null}
                    <Button
                      disabled={busy}
                      onClick={() => advance("resolved", "treated")}
                    >
                      Record outcome and close
                    </Button>
                  </div>
                ) : (
                  <p className="text-xs text-ink-muted">
                    Closed {relativeTime(item.closed_at)}
                    {item.outcome ? ` · ${titleise(item.outcome)}` : ""}
                  </p>
                )}
              </div>
            )}
          </div>
        ) : null}
      </Card>
    </li>
  );
}

function Detail({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-ink-muted">{label}</dt>
      <dd className="mt-0.5 text-ink">{value}</dd>
    </div>
  );
}

function titleise(value: string): string {
  return value.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());
}
