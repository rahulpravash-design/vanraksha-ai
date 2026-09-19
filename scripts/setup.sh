#!/usr/bin/env bash
# One-time local setup: installs the engine, the API, and the web app into
# their own environments. Safe to re-run.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

echo "==> AI engine (services/ai-engine)"
python3 -m venv .venv 2>/dev/null || true
# shellcheck disable=SC1091
source .venv/bin/activate
pip install -q --upgrade pip
pip install -q -e "services/ai-engine[dev]"

echo "==> API (services/api)"
pip install -q -e "services/api[dev]"

echo "==> Web app (apps/web)"
(cd apps/web && npm install --no-audit --no-fund)

echo
echo "Setup complete. Next: ./scripts/dev.sh"
