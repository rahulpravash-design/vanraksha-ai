"""Vercel serverless entrypoint for the VANRAKSHA API.

The monorepo keeps the API and the engine as two installable packages under
``services/``. Rather than pip-installing local paths during a serverless
build -- which is fragile on a read-only filesystem -- this puts both source
roots on ``sys.path`` and imports the app directly. ``requirements.txt`` then
only has to carry genuine third-party dependencies.

Everything under ``/`` is routed here by ``vercel.json``, so this single
function serves the whole API including ``/docs`` and ``/health``.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

for source_root in (ROOT / "services" / "api", ROOT / "services" / "ai-engine"):
    path = str(source_root)
    if path not in sys.path:
        sys.path.insert(0, path)

from app.main import app  # noqa: E402  (path setup must run first)

__all__ = ["app"]
