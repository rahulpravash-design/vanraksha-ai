#!/usr/bin/env bash
#
# Seed a remote PostgreSQL database with the demo district.
#
# The API creates its tables on boot, but the demo data has to be loaded once
# from a machine that can reach the database. Run this after setting the
# database URL on the API project and before the first demo.
#
#   ./scripts/seed-remote.sh "postgresql://user:pass@host/db?sslmode=require"
#
# Re-running drops and recreates the demo rows, so it is safe to repeat before
# a demo -- and the cluster reveal only works on a freshly seeded database.

set -euo pipefail

DSN="${1:-${VANRAKSHA_DATABASE_URL:-}}"

if [[ -z "$DSN" ]]; then
  echo "usage: $0 <postgres-dsn>" >&2
  echo "   or: VANRAKSHA_DATABASE_URL=... $0" >&2
  exit 2
fi

case "$DSN" in
  postgres://*|postgresql://*|postgresql+psycopg://*) ;;
  *)
    echo "error: expected a PostgreSQL DSN, got: ${DSN%%:*}:..." >&2
    exit 2
    ;;
esac

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ ! -d .venv ]]; then
  echo "No .venv found. Run ./scripts/setup.sh first." >&2
  exit 1
fi

# psycopg is an optional extra locally; the deployment always has it.
if ! .venv/bin/python -c "import psycopg" 2>/dev/null; then
  echo "Installing the PostgreSQL driver..."
  .venv/bin/pip install --quiet "psycopg[binary]>=3.2"
fi

echo "Seeding ${DSN%%@*}@..."
cd services/api
VANRAKSHA_DATABASE_URL="$DSN" \
VANRAKSHA_ENVIRONMENT=development \
  ../../.venv/bin/python -m app.cli seed --days 90

echo
echo "Done. The demo accounts above all share the printed password."
