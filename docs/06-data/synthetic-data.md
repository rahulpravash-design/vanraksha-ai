# Synthetic data

Every livestock health record in this repository — the API's demo seed and
the `ml/` evaluation scenarios — is synthetic. None of it is drawn from real
herds, real farmers, or real disease events.

## Why synthetic, and why that is disclosed everywhere

A hackathon team has no legitimate path to real veterinary surveillance data
in the time available, and pretending otherwise would be dishonest and would
produce evaluation numbers nobody should trust. So instead:

- Every generator (`services/api/app/seed.py`,
  `ml/generate_dataset.py`) writes a `notice` field into its own
  output stating the data is synthetic.
- Generation is **seeded and reproducible** — the same seed produces the same
  dataset — specifically so that a demo is rehearsable and a change in a
  measured evaluation number means the code changed, not that new random data
  happened to look different.
- Background reporting rates, symptom-presentation mixes, and outbreak growth
  curves are shaped to be *plausible* (informed by general epidemiological
  reasoning about syndromic surveillance) but are not fitted to any real
  dataset and carry no claim about real-world prevalence.

## What each dataset is for

- **API demo seed** — a synthetic district (8 villages, ~28 farms, ~200
  animals) with realistic background reporting plus one injected respiratory
  outbreak and one injected severe standalone case, so the full product story
  (report → triage → cluster → case → dashboard) can be demonstrated.
- **`ml/data/synthetic/scenarios.json`** — 30 background-only and 30
  single-outbreak scenarios, purpose-built so the cluster detector's false
  alert rate and detection rate can be *measured against a known answer*
  rather than asserted.

## Path to real data

A field pilot requires a data-sharing agreement with a district veterinary
department or an ICAR institute, an IRB-equivalent consent process for
farmer-identifiable data, and a validation period where the engine's output is
compared against veterinary ground truth before any triage decision is
trusted operationally. None of that exists yet; this repository's synthetic
data is explicitly a stand-in for it, not a substitute.
