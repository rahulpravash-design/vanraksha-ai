# AI limitations and safety boundaries

This is the single most important document in the repository for judges,
reviewers, and anyone deploying this beyond a demo. Read it before trusting
any output from this system.

## What the engine is entitled to say

The engine identifies **syndromic patterns** (a clustering of clinical signs —
"respiratory syndrome," "vesicular syndrome") and scores **urgency**. Both are
supportable from a field report. Neither requires — and neither claims —
knowledge of which pathogen is responsible.

## What it is never entitled to say, and where that is enforced

| Claim | Where it is blocked |
|---|---|
| "This animal has disease X" | Never generated. `StatutoryCaution` objects are phrased as "consistent with," never as a diagnosis — enforced by a unit test (`test_no_caution_claims_a_diagnosis`) that scans every caution's text for diagnostic phrasing. |
| A medicine, dose, or route | The assistant's *input* is screened for a prescription-shaped question and redirected before generation (`assistant/safety.py: screen_request`); its *output* is independently scanned for dose-shaped text (`mg`, `ml`, "inject...") and replaced if found (`screen_response`) — so a prompt-injected or unusually phrased request still cannot make it through. |
| A fabricated statistic | The grounded assistant's `_is_grounded` check rejects any number in generated text that does not appear in the structured context it was given. Tested with a deliberately lying stub model (`test_a_hallucinating_model_is_rejected`). |

## The triage vignette set is not clinical validation

`ml/triage_vignettes.json` contains 24 expected-band assertions written by the
project team from published veterinary triage principles. They are **not**
reviewed by a practising veterinarian. A 24/24 pass means the engine's rules
do what the project intended — a real regression guarantee, and the same
mechanism that caught six genuine under-triage bugs during development (see
the commit fixing `FLOOR.*` rules in the risk engine) — but it is not evidence
of clinical correctness. Do not present it as such. The next real step before
any field pilot is veterinary review of this file, followed by expanding it
well past 24 cases.

## The cluster detector's guarantees are statistical, not epidemiological

A detected cluster means: several reports are close in space, close in time,
and share a syndromic profile, at a rate above what the detector's tuned
parameters treat as expected. It does **not** mean a specific disease is
present, confirmed, or even likely — that determination is explicitly left to
the veterinary reviewer, whose verdict (`ClusterReview`) is recorded as the
ground truth the detector's own precision is measured against.

## Synthetic data

Every dataset in `ml/data/synthetic/` and the API's demo seed
(`services/api/app/seed.py`) is synthetic, seeded, and reproducible. It is
shaped to be plausible (seasonal background load, a believable outbreak growth
curve) so the workflow can be exercised end to end. **It carries no claim about
real-world disease prevalence** and every generator and seed script says so in
its own output. See `docs/06-data/synthetic-data.md`.

## Production pathway

Before any field deployment: veterinary review of the vignette set and the
statutory-caution catalogue, a validated field dataset replacing the synthetic
one, PostGIS-backed spatial queries at scale, and a formal model card
versioned alongside the engine's semantic version (already exposed as
`engine_version` / `detector_version` on every output — the plumbing for this
exists; the review process does not yet).
