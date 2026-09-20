# VANRAKSHA AI

**Field-to-response intelligence for livestock health surveillance.**

VANRAKSHA AI turns a farmer's field observation into an explainable risk score,
checks it against nearby reports for an emerging cluster, and routes the work
to the right veterinary staff — built for intermittent connectivity and
incomplete records, and for the case where a single report is not enough to
say anything, but five nearby reports are.

> Submission for Smart India Hackathon problem statement **SIH26128** —
> *Efficient systems for early detection, prevention, and management of
> livestock diseases and animal health issues.*

## Why this and not a disease-prediction dashboard

India already has serious livestock disease-forecasting infrastructure —
ICAR-NIVEDI's NADRES-V2 forecasts district-level risk for major diseases using
GIS and ML. Building another version of that is not a differentiated project.

**This project sits one layer earlier and one layer more operational.** It is
not a forecaster; it is the field-to-response loop that turns a raw
observation into a triaged, geo-temporally cross-checked, routed piece of
veterinary work — the layer where the actual delay in India's livestock
disease response happens today. The architecture is designed so validated
output from this layer could feed a district-level forecasting system like
NADRES-V2, not compete with one.

| | A forecasting platform | VANRAKSHA AI |
|---|---|---|
| Input | Historical + environmental data | Live field reports, online or queued offline |
| Output | District-level risk map | A scored, explained case + a routed alert |
| Grain | District / block | Individual animal → village → block → district |
| When it helps | Planning, resource allocation | The hour after a farmer notices something |

## What it actually does — and refuses to do

- **Identifies syndromic patterns and scores urgency.** It never names a
  disease. Every case is described as "consistent with a vesicular
  presentation," never "this animal has FMD."
- **Detects geo-temporal clusters** — reports close in distance, close in
  time, and similar in presentation — because a single report can never
  establish that something unusual is happening in an area; five related ones
  can.
- **Routes and tracks the response**, not just the alert: a case queue ordered
  by urgency and time-to-deadline, assignment, and a recorded outcome, which is
  also what makes the system's own performance measurable.
- **Never recommends a medicine, a dose, or a route of administration** — not
  from a rule, and not from a language model. The assistant's output is
  scanned for dosage-shaped text and blocked regardless of how it was produced.

## Evidence, not claims

Every quality figure below comes from a runnable evaluation script against
data where the answer is known, not from an assertion.

**Cluster detector** (`ml/evaluate_detector.py`, synthetic scenarios with a
known injected outbreak):

| Metric | Value |
|---|---|
| Outbreaks detected | 100% (all injected events found) |
| False clusters per outbreak-free district per scan | 0.13 |
| Median detection delay | 63 h (≈ 3 daily sweeps) |
| Alert precision | 0.75 |

A parameter sweep across radius/window/min-reports found that the naive
default (`min_reports=3`) produced **11× more false alerts** for the same
detection rate — see `ClusterConfig`'s docstring in
`services/ai-engine/vanraksha_ai/clustering/geo_temporal.py` for the full
trade-off. This is not a tuning anecdote; it is the mechanism by which the
project's own tests caught a real problem before it reached a field pilot.

**Triage engine** (`ml/evaluate_triage.py`, 24 hand-authored clinical
vignettes — see the honesty note below):

| Metric | Value |
|---|---|
| Vignettes meeting expectation | 24 / 24 |
| Escalation recall (needed a vet → got escalated) | 1.00 |
| Escalation precision (escalated → actually needed it) | 1.00 |

**Honesty note:** the vignette expectations were authored by the project team
from published veterinary triage principles, not ratified by a practising
veterinarian. A perfect score means *the engine does what the project
intended* — a real and useful regression guarantee — not that the intention is
clinically correct. `ml/triage_vignettes.json` and every evaluation script say
this explicitly; treat it as a floor to build on, not a certification.

## Architecture

```
Farmer / field worker
        │  (online or queued offline in IndexedDB)
        ▼
┌─────────────────────────┐
│  Next.js web / PWA       │  apps/web
└──────────┬───────────────┘
           │ REST (JWT, role + geo scoped)
           ▼
┌─────────────────────────┐      ┌──────────────────────────┐
│  FastAPI + SQLAlchemy    │─────▶│  vanraksha_ai engine       │
│  services/api            │      │  services/ai-engine        │
│  auth · reports · cases  │      │  taxonomy · risk · cluster │
│  surveillance · audit    │      │  anomaly · assistant       │
└──────────┬────────────────┘      └──────────────────────────┘
           │
           ▼
   PostgreSQL (prod) / SQLite (dev)
```

The engine has **zero third-party runtime dependencies** — it imports and
tests identically inside the API container, a notebook, or the `ml/` scripts,
which is what makes an evaluation harness meaningful: the code under test is
exactly the code that runs in production.

## Quick start

### One command (verified — recommended for a demo)

```bash
./scripts/setup.sh     # once: creates a venv, installs engine + API + web deps
./scripts/dev.sh        # every time: seeds a demo district on first run, starts both services
```

Open http://localhost:3000/login. Demo account emails and the shared password
(`VanrakshaDemo2026!`) are printed the first time `dev.sh` seeds the database;
delete `vanraksha.db` and re-run to see them again. `Ctrl+C` stops both
services. This was run end to end in this environment: seed → login → both
`/docs` and `/login` returning 200 → a real token issued.

For a guided walk through the seeded district — which account to use, which
village holds the injected outbreak, and what each screen shows — see
[`docs/demo-script.md`](docs/demo-script.md). The pitch deck is checked in as
[`docs/pitch-deck.html`](docs/pitch-deck.html): a single file that opens from
disk with its fonts embedded, so it needs no network.

### Deployed

| | |
|---|---|
| Web | <https://vanraksha-livestock-web.vercel.app> |
| API | <https://vanraksha-api.vercel.app> (`/docs` for the OpenAPI UI) |

Both build and deploy from this branch. **The API needs a PostgreSQL database
before it will serve anything**: it refuses to boot on SQLite outside
development, deliberately, because a demo silently running on a per-instance
SQLite file would lose every report between requests. Set
`VANRAKSHA_DATABASE_URL` on the API project, redeploy, then load the demo
district once:

```bash
./scripts/seed-remote.sh "postgresql://user:pass@host/db?sslmode=require"
```

See [`docs/10-deployment/deployment.md`](docs/10-deployment/deployment.md) for
the full procedure and the two failures that only appear in a hosted deploy.

### Docker

```bash
docker compose up --build
docker compose exec api python -m app.cli seed --days 90
```

Open http://localhost:3000. Sign in the same way as above. *(Docker images
are written for this but not build-verified in this authoring environment —
no daemon was available here; `./scripts/dev.sh` above was.)*

### Manual, step by step

```bash
# 1. AI engine + API
cd services/ai-engine && pip install -e ".[dev]" && pytest      # 150+ tests
cd ../api && pip install -e ".[dev]"
export VANRAKSHA_DATABASE_URL="sqlite:///./vanraksha.db"
python -m app.cli seed --days 90      # synthetic district, prints accounts
uvicorn app.main:app --reload --port 8000

# 2. Web app (separate shell)
cd apps/web && npm install
NEXT_PUBLIC_API_BASE=http://localhost:8000/api/v1 npm run dev
```

Open http://localhost:3000/login.

### Run the evaluations yourself

```bash
cd ml
python generate_dataset.py --scenarios 30       # writes labelled scenarios
python evaluate_detector.py --sweep              # cluster parameter sweep
python evaluate_triage.py                        # 24 clinical vignettes
```

## Repository layout

```
apps/web/               Next.js app — field reporting, dashboards, case queue,
                         cluster review, 2D map, 3D command centre
services/ai-engine/      Dependency-free triage/clustering/anomaly engine
services/api/            FastAPI + SQLAlchemy: auth, reports, cases, sweep
ml/                      Synthetic data generation + evaluation harnesses
docs/                    Problem framing, architecture, AI limitations,
                         the demo run sheet, and the pitch deck
docker-compose.yml       One-command local stack
```

## Test status

- `services/ai-engine`: unit tests over every module (taxonomy normalisation,
  risk scoring including every statutory caution and clinical floor, cluster
  geometry and detection, anomaly statistics, evaluation metrics, assistant
  guardrails, end-to-end pipeline).
- `services/api`: integration tests through a real FastAPI `TestClient` — auth
  and access control, offline sync and idempotency, the full report → triage →
  case lifecycle, cluster detection and review, dashboard aggregation scoped
  by role, and the demo seed itself (including that it stays reproducible and
  that the injected outbreak is actually detected).
- `apps/web`: builds clean under `next build` with TypeScript strict mode; the
  full flow (login → file a report → see the triage verdict and handling
  precautions → dashboard → cluster review → map → 3D district view) was
  driven end to end with Playwright against the running stack, in both light
  and dark themes.

Run everything:

```bash
(cd services/ai-engine && pytest -q)
(cd services/api && pytest -q)
(cd apps/web && npm run build)
```

## What is deliberately not built

Real government/NADRES integration, native mobile apps, SMS gateways,
multilingual UI strings beyond the architecture for them, and a
veterinarian-ratified vignette set are explicit roadmap items, not oversights
— see `docs/roadmap/` for the phased plan. The 36–hackathon-hour version of
this project is everything above the line; production hardening (PostGIS,
Alembic migrations, real secret management, WAHIS/ICAR data exchange) is the
next phase.

## License

MIT — see `LICENSE`.
