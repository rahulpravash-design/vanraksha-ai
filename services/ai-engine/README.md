# VANRAKSHA AI Engine

The reasoning core of the platform, packaged as a standalone Python library
with **no third-party runtime dependencies**. It imports cleanly inside the API
container, a notebook, a batch job, or a bare test harness.

## What is in here

| Module | Responsibility |
| --- | --- |
| `taxonomy` | Controlled vocabulary for clinical signs; collapses free-text synonyms (including negation) onto stable codes and syndromic groups. |
| `risk` | Deterministic, fully attributable triage scoring, plus the statutory-caution catalogue that can raise a band regardless of the arithmetic. |
| `clustering` | Geo-temporal-syndromic cluster detection (DBSCAN over a domain-specific neighbourhood predicate). |
| `anomaly` | Aberration detection on report-count series: Poisson exceedance plus an EWMA control limit. |
| `trends` | Zero-filled time-series construction and plain-language trend description. |
| `assistant` | Grounded summarisation with mandatory input and output guardrails; an LLM is optional and strictly downstream. |
| `evaluation` | The metrics that actually matter here — escalation recall, alert precision, detection delay. |
| `pipeline` | Orchestration: report → triage → cluster → aberration check → routed alert. |

## Quick start

```python
from datetime import datetime
from vanraksha_ai import Observation, assess

result = assess(Observation(
    report_id="R-1",
    species="cattle",
    reported_at=datetime.utcnow(),
    symptoms=["fever", "mouth ulcer", "drooling"],
    temperature_c=40.4,
    herd_size=20,
    affected_count=4,
))

print(result.band.value)              # 'urgent'
for c in result.contributions:
    print(f"{c.points:+.1f}  {c.factor}: {c.evidence}")
```

Every number the engine produces can be traced to a named rule. That is the
point: a veterinarian who disagrees with a score can see exactly which rule to
argue with.

## What this engine will not do

It does not name diseases and it does not recommend treatments or doses. It
identifies **syndromic patterns**, scores urgency, detects clusters, and routes
work. Diagnosis and treatment stay with qualified veterinary and laboratory
processes — see [`docs/05-ai/limitations.md`](../../docs/05-ai/limitations.md).

## Tests

```bash
pip install -e ".[dev]"
pytest
```
