# Problem statement — SIH26128

**Efficient systems for early detection, prevention, and management of
livestock diseases and animal health issues.**

## The actual gap

The problem is not "predict livestock disease." India already has serious
infrastructure for that — ICAR-NIVEDI's NADRES-V2 forecasts district-level
risk for 15+ diseases using GIS and ML, delivered to farmers and vets via
SMS/digital advisories.

The gap this project targets sits **earlier and more operational**: a farmer
notices something is wrong, and the chain from that moment to a veterinary
response is fragmented, slow, and rarely aggregated across nearby farms in
real time. Nobody's forecasting model can act on an observation it never
received in a structured form.

```
TODAY
Farmer ──X──> Field Worker ──X──> Vet ──X──> Lab
   fragmented, delayed, paper/phone-based information

RESULT: risk identified late → response starts late
```

## Root cause

Information flow, not information science. The individual pieces (a
veterinarian's judgement, a lab's diagnostic capability) work; what is missing
is the connective layer that:

1. captures an observation in a structured, analysable form regardless of
   connectivity,
2. assesses it against explainable rules so a non-specialist reader can trust
   and act on the output,
3. checks it against nearby reports for a pattern a single report cannot
   reveal, and
4. routes and tracks the resulting work to a recorded outcome.

## Stakeholders

- **Primary**: livestock owners, field veterinarians, para-veterinary workers
- **Secondary**: veterinary hospitals, diagnostic labs, district/block
  officers, state animal husbandry departments
- **Indirect**: consumers, public health (several syndromes here are
  zoonotic), livestock supply chains

## Scope of this submission

Built and tested: field reporting (online + offline), symptom normalisation,
explainable triage with statutory handling cautions, geo-temporal cluster
detection, aberration detection, a veterinary case queue, cluster review as a
measurable ground truth, role/geography-scoped dashboards, a grounded
assistant with hard safety guardrails, and an evaluation harness that measures
all of the above against data with a known answer.

Explicitly out of scope for this submission: real NADRES/WAHIS integration,
native mobile apps, SMS delivery, and a veterinarian-ratified vignette set —
see `docs/roadmap/`.
