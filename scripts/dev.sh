#!/usr/bin/env bash
# Starts the API and the web app together for local demo/dev use.
# Run ./scripts/setup.sh first. Ctrl+C stops both.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

# shellcheck disable=SC1091
source .venv/bin/activate

export VANRAKSHA_DATABASE_URL="${VANRAKSHA_DATABASE_URL:-sqlite:///$(pwd)/vanraksha.db}"

if [ ! -f vanraksha.db ]; then
  echo "==> No database found — seeding a 90-day demo district"
  (cd services/api && python -m app.cli seed --days 90)
fi

cleanup() {
  echo
  echo "==> Stopping"
  kill "${API_PID:-}" "${WEB_PID:-}" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

echo "==> Starting API on :8000"
(cd services/api && uvicorn app.main:app --port 8000) &
API_PID=$!

echo "==> Starting web app on :3000"
(cd apps/web && NEXT_PUBLIC_API_BASE=http://localhost:8000/api/v1 npm run dev) &
WEB_PID=$!

echo
echo "API:  http://localhost:8000/docs"
echo "Web:  http://localhost:3000/login"
echo "(demo account emails/passwords were printed when the database was seeded —"
echo " re-run 'cd services/api && python -m app.cli seed --days 90' to see them again"
echo " if you already have a database, delete vanraksha.db first)"
echo

wait
