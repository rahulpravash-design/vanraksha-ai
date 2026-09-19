# System architecture

## Layers

```
apps/web (Next.js 16, TypeScript, hand-rolled SVG charts + Three.js)
    │  REST over HTTPS, JWT bearer auth
    ▼
services/api (FastAPI + SQLAlchemy 2.0)
    │  imports as a library — no network hop
    ▼
services/ai-engine (vanraksha_ai — zero runtime dependencies)
    │
    ▼
PostgreSQL (production) / SQLite (dev, single file)
```

## Why the engine is a separate, dependency-free package

`services/ai-engine` has **no third-party runtime imports** — no
FastAPI, no SQLAlchemy, no numpy. This is deliberate:

1. **It is the thing being evaluated.** `ml/evaluate_detector.py` and
   `ml/evaluate_triage.py` import it directly. If the engine depended on the
   web framework, "evaluate the engine" and "stand up a server" would be the
   same task, and the evaluation harness would test infrastructure it doesn't
   need to.
2. **It is the thing the API wraps, not extends.** `services/api/app/services/
   triage.py` and `surveillance.py` are the only places that translate
   between ORM rows and the engine's plain dataclasses. Business logic about
   *what a risk score means* lives in exactly one place.
3. **It runs anywhere** — inside the API process, in a notebook, in a CI job,
   or in a future batch/streaming pipeline — without carrying a web server
   along.

## Request flow: a field report

```
POST /api/v1/reports
   │
   ├─ Pydantic validation (species known, affected ≤ herd, dates sane, …)
   ├─ services/triage.py: build an Observation from the ORM row
   │     + vaccination status derived from the animal's own records
   │     + prior-report count in the last 14 days
   │     + whether this report already falls inside a live cluster
   ├─ vanraksha_ai.risk.assess(observation)
   │     → RiskAssessment: score, band, every contributing rule with its
   │       evidence string, any statutory cautions, a response deadline
   ├─ persisted as RiskAssessmentRecord (immutable once written; a
   │     re-assessment replaces it explicitly, never silently)
   └─ case opened automatically if the band is priority or above,
         with a due_at computed from the report's own reported_at —
         not the wall clock at triage time (this matters for backfills)
```

## Request flow: a surveillance sweep

```
POST /api/v1/surveillance/sweep
   │
   ├─ load reports with coordinates in the trailing window
   ├─ vanraksha_ai.clustering.detect_clusters(points, config)
   │     DBSCAN over a domain-specific neighbourhood predicate:
   │     within radius_km AND within window_hours AND
   │     syndromic-profile Jaccard similarity ≥ min_similarity
   ├─ each cluster is upserted by a stable signature (hash of its sorted
   │     member report ids) — a repeated sweep finds the same cluster and
   │     updates it, never duplicates it
   ├─ a cluster a reviewer already dismissed is never re-raised as new
   └─ alerts are routed by role (veterinarian, block_admin, district_admin
         once severity crosses a threshold) and deduplicated by the same
         signature
```

## Access control

Two dimensions, both enforced at the query layer, not the UI:

- **Role** decides what actions are permitted (a farmer files reports; a
  veterinarian closes cases; treatments can only be recorded by a clinical
  role).
- **Geographic scope** decides whose records are visible — a district
  officer's `visible_scope()` resolves to their district, a field worker's to
  their block, a farmer's to their own farms — and every list/aggregate
  endpoint applies that scope inside the SQL query (`services/analytics.py:
  apply_scope`), not by filtering a response after the fact.

## Offline-first field reporting

A report is written to an IndexedDB outbox keyed on a client-generated UUID
*before* any network call is attempted. If the request fails for a retryable
reason (no connection, 5xx), it stays queued; a non-retryable rejection (bad
data) is surfaced to the user instead of retried forever. On reconnect, the
whole outbox is flushed in one batch to `/reports/sync`, where each item is
settled independently — one malformed report does not cost the farmer the
rest of a week's queued work — and the server treats a replayed
`client_uuid` as a duplicate, not a new report.
