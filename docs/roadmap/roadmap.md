# Roadmap

## Built (this submission)

- Symptom taxonomy: free-text/voice normalisation with negation handling,
  synonym collapse, syndromic grouping
- Explainable risk engine: additive scoring where every point traces to a
  named rule, plus clinical band floors and a statutory-caution catalogue for
  patterns where the correct first action is procedural, not arithmetic
- Geo-temporal-syndromic cluster detection (DBSCAN over distance + time +
  presentation similarity), tuned against a labelled synthetic evaluation set
- Poisson + EWMA aberration detection on report-volume time series
- Grounded assistant with hard input/output safety guardrails (no diagnosis,
  no prescription, no unsupported numbers)
- Full API: auth, offline sync, report/case/cluster lifecycle, role+geography
  scoped analytics, audit log
- Web app: field reporting (voice, offline queue), veterinary case queue,
  cluster review, dashboards, a projected-SVG map, a WebGL district command
  view
- Evaluation harness with reproducible synthetic data for both the cluster
  detector and the triage engine

## Next (production pathway, not attempted here)

1. **Veterinary review** of the triage vignette set and statutory-caution
   catalogue — the single highest-priority item before any field use.
2. **PostGIS** for spatial queries at scale; the current O(n²) detector is
   fine for a district-sized trailing window and documented as needing an
   index past that.
3. **Alembic migrations** replacing `create_all` for anything beyond local dev.
4. **Real secrets management** — the current `.env`-based config already
   refuses to boot in production with the dev key or with SQLite; a KMS/vault
   integration is the next step.
5. **SMS/USSD delivery** for farmers without a smartphone, and completed
   multilingual UI strings (the `language` field and i18n architecture exist;
   translated content does not yet).
6. **A real integration pathway to NADRES-V2 / WAHIS** — validated,
   veterinarian-reviewed cluster data flowing outward, not this system
   attempting to replace district-level forecasting.
7. **A validated field dataset** replacing the synthetic one, under a proper
   data-sharing and consent agreement with a district veterinary department.
