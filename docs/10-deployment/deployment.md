# Deployment

VANRAKSHA runs as two Vercel projects against one managed PostgreSQL database.

```
Browser
   │
   ├── vanraksha-livestock-web     Next.js, apps/web
   │        │  NEXT_PUBLIC_API_BASE (baked at build time)
   │        ▼
   └── vanraksha-livestock-api     FastAPI as a serverless function, api/index.py
            │
            ▼
        PostgreSQL (managed)
```

## Why two projects

The web app's API base URL is inlined at build time by Next.js, so the API has
to exist before the web app is built. Deploy order is therefore always:
**API first, then web.**

## The API as a serverless function

`api/index.py` puts `services/api` and `services/ai-engine` on `sys.path` and
imports the FastAPI app. It does not pip-install the local packages: installing
a local path during a build on a read-only filesystem is fragile, and this
keeps `requirements.txt` to genuine third-party dependencies.

`vercel.json` rewrites every path to that one function, so `/health`, `/docs`
and `/api/v1/*` are all served by the same app.

### Two things that only break in a deployment

**Connection pooling.** Each serverless invocation may run in a fresh process,
so a pooled PostgreSQL connection is never reused — it holds a server slot open
that nothing will claim again, and enough concurrent invocations exhaust the
connection limit. `services/api/app/db.py` switches to `NullPool` when `VERCEL`
is set. Local runs and SQLite are untouched.

**The driver in the DSN.** Managed providers hand out a driverless URL —
`postgres://` from Heroku-lineage services, `postgresql://` from most others.
SQLAlchemy resolves a bare `postgresql` scheme to psycopg2, which this project
does not install; it uses psycopg 3. The result is a crash on first connection
that no local run or CI job can reproduce, because those use SQLite.
`Settings._normalise_postgres_dsn` rewrites both spellings to
`postgresql+psycopg://`, so an operator can paste whatever their provider gave
them. Six tests cover it.

## Environment variables

### API project

| Variable | Required | Notes |
|---|---|---|
| `VANRAKSHA_DATABASE_URL` | **Yes** | Any managed PostgreSQL DSN. The driver is normalised automatically. |
| `VANRAKSHA_SECRET_KEY` | **Yes** | ≥32 bytes. `python -c "import secrets; print(secrets.token_urlsafe(48))"` |
| `VANRAKSHA_ENVIRONMENT` | Yes | `production` |
| `VANRAKSHA_CORS_ORIGINS` | Yes | The web app's origin, comma-separated for several |

`Settings.validate_for_runtime` refuses to start on SQLite or on the shipped
development signing key when the environment is production. That is deliberate:
a platform holding animal-health records and farmer contact details should not
boot with a shipped key, and a demo that silently runs on SQLite in production
would lose every report between requests.

### Web project

| Variable | Required | Notes |
|---|---|---|
| `NEXT_PUBLIC_API_BASE` | Yes | `https://<api-host>/api/v1`. Inlined at build time — changing it needs a rebuild, not just a restart. |

## First deploy

```bash
# 1. API
#    Root directory: repository root. Framework: leave unset (do NOT pick
#    "fastapi" from the preset list -- see "Settings that bite" below).
#    Set the four variables above, then deploy.

# 2. Create the schema and demo data, once, from a machine that can
#    reach the database:
export VANRAKSHA_DATABASE_URL="postgresql://..."
cd services/api && python -m app.cli seed --days 90

# 3. Web
#    Root directory: apps/web. Framework: nextjs.
#    Set NEXT_PUBLIC_API_BASE to the API URL, then deploy.

# 4. Set the API's VANRAKSHA_CORS_ORIGINS to the web URL and redeploy the API.
```

Tables are created on boot by `Base.metadata.create_all`, so step 2 is only
needed to load the demo district.

## Settings that bite

**Vercel Authentication is on by default.** A new project ships with
`ssoProtection` set to `all_except_custom_domains`, which puts a Vercel login
in front of the deployment — fine for a private preview, fatal for a demo an
evaluator is meant to open. Turn it off in Project → Settings → Deployment
Protection.

**Root directory on a monorepo.** The web project must have its root directory
set to `apps/web`, or the build fails with `NEXT_NO_VERSION` because there is
no `package.json` at the repository root. The API project uses the repository
root, because it needs `services/`.

**Do not set the API project's framework preset to `fastapi`.** It looks like
the obviously correct choice, and it is wrong for this repository. Vercel's
FastAPI preset expects its own build convention and does not route traffic
through `vercel.json`'s rewrite the way a plain Python function does. With the
preset set, the deployment builds and reports `READY`, but every request --
including `/health` -- gets an instant platform-level 404
(`x-response-time-ms` under 1, versus 50+ for a real response), because the
request never reaches `api/index.py` at all. The build succeeding is not
evidence the routing works; only a real request is.

The fix is to leave the project's framework **unset** (`null`). That is the
standard pattern for a hand-written `api/index.py` + `vercel.json` rewrite,
and it is what this project's API project is configured with. If a future
redeploy is ever created with `framework: "fastapi"` in `projectSettings`,
undo it: `PATCH` the project with `{"framework": null}` and redeploy.

**A CORS origin from a plain environment string crashes `Settings()` unless
the field is marked `NoDecode`.** This is a Python/pydantic-settings issue,
not a Vercel one, but it only ever shows up in a real deployment: no local run
or test sets `VANRAKSHA_CORS_ORIGINS` as an environment string, so nothing
local exercises the code path that broke. See the fix in
`services/api/app/config.py` and its regression tests in
`services/api/tests/test_meta.py::TestCorsOriginsFromEnvironment` before
touching that field again.

**A green build is not a working deployment.** Both bugs above shipped a
`READY` deployment that was completely non-functional. The only reliable
check is a real request against the live URL -- `curl` from an environment
with real network access, not just "the build succeeded."

## Other hosts

The repository also carries a working `docker-compose.yml` and two Dockerfiles.
A single container on a host with a persistent disk is a simpler deployment
than serverless — no connection-pool concern, and SQLite would be viable — but
those images have never been build-verified, because no Docker daemon has been
available in any environment this project was authored in. Treat them as
written-but-unproven.
