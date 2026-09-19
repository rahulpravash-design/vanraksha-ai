#!/usr/bin/env python3
"""Generate labelled synthetic surveillance scenarios.

**Everything produced here is synthetic.** The point is not to imitate real
prevalence -- it cannot, and any claim built on that would be dishonest. The
point is to produce data where *the answer is known*, so detector behaviour can
be measured rather than asserted:

* a **background** scenario has no outbreak in it at all, so every cluster the
  detector raises is a false alert, and the rate is measurable;
* an **outbreak** scenario has one injected event with a known village, start
  time and size, so detection rate and detection delay are measurable.

Generation is seeded, so a run is reproducible and a change in the measured
numbers means the detector changed, not the dice.

    python ml/generate_dataset.py --scenarios 40 --out ml/data/synthetic
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services" / "ai-engine"))

from vanraksha_ai.taxonomy import BY_CODE  # noqa: E402

# A district's worth of villages, laid out on a plausible grid.
VILLAGE_COUNT = 8
VILLAGE_SPACING_KM = 9.0
ORIGIN = (13.07, 77.79)

#: Everyday complaints and their relative frequency. Weighted so the ordinary
#: dominates, because in the field it does -- a detector tuned on data where a
#: quarter of reports are outbreaks will drown a real district in alerts.
BACKGROUND = [
    (["reduced_appetite"], 14),
    (["milk_drop"], 12),
    (["lameness"], 10),
    (["ectoparasites"], 9),
    (["diarrhoea"], 9),
    (["fever", "lethargy"], 8),
    (["udder_swelling", "abnormal_milk"], 7),
    (["skin_lesions"], 6),
    (["nasal_discharge"], 6),
    (["retained_placenta"], 4),
    (["infertility"], 4),
    (["bloat"], 3),
    (["weight_loss"], 3),
    (["swelling"], 2),
]

#: Injected events, by the syndromic shape they present with.
OUTBREAK_PROFILES = {
    "respiratory": [
        ["fever", "nasal_discharge"], ["fever", "cough"],
        ["fever", "cough", "nasal_discharge"], ["cough", "dyspnoea"],
        ["fever", "cough", "lethargy"],
    ],
    "enteric": [
        ["diarrhoea"], ["diarrhoea", "dehydration"],
        ["diarrhoea", "reduced_appetite"], ["bloody_diarrhoea"],
        ["diarrhoea", "lethargy"],
    ],
    "vesicular": [
        ["oral_lesions", "salivation"], ["oral_lesions"],
        ["foot_lesions", "lameness"], ["oral_lesions", "foot_lesions"],
        ["salivation", "reduced_appetite"],
    ],
}

SPECIES_MIX = [("cattle", 0.46), ("buffalo", 0.19), ("goat", 0.24), ("sheep", 0.11)]


@dataclass
class SyntheticReport:
    report_id: str
    village_id: str
    latitude: float
    longitude: float
    observed_at: str
    symptom_codes: list[str]
    species: str
    affected_count: int
    deaths_count: int
    herd_size: int
    #: The label. True only for reports belonging to the injected event.
    is_outbreak: bool


@dataclass
class Scenario:
    scenario_id: str
    kind: str                      # "background" | "outbreak"
    days: int
    reports: list[SyntheticReport] = field(default_factory=list)
    # Ground truth, present only for outbreak scenarios.
    outbreak_village: str | None = None
    outbreak_syndrome: str | None = None
    outbreak_start: str | None = None
    outbreak_size: int = 0

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["reports"] = [asdict(r) for r in self.reports]
        return payload


def _villages() -> list[dict]:
    """A ring of villages around the origin, spaced far enough apart that they
    do not merge into one cluster by proximity alone."""
    out = []
    km_per_deg_lat = 110.574
    km_per_deg_lon = 111.320 * math.cos(math.radians(ORIGIN[0]))
    for index in range(VILLAGE_COUNT):
        angle = 2 * math.pi * index / VILLAGE_COUNT
        radius = VILLAGE_SPACING_KM * (1.6 if index % 2 else 1.0)
        out.append({
            "id": f"V{index + 1:02d}",
            "lat": ORIGIN[0] + (radius * math.sin(angle)) / km_per_deg_lat,
            "lon": ORIGIN[1] + (radius * math.cos(angle)) / km_per_deg_lon,
        })
    return out


def _species(rng: random.Random) -> str:
    roll = rng.random()
    total = 0.0
    for name, share in SPECIES_MIX:
        total += share
        if roll <= total:
            return name
    return "cattle"


def _jitter(rng: random.Random, value: float, km: float) -> float:
    return value + rng.uniform(-km, km) / 111.0


def generate_scenario(
    scenario_id: str,
    *,
    kind: str,
    rng: random.Random,
    days: int = 60,
    daily_rate: float = 2.4,
    outbreak_size: int = 9,
    outbreak_span_days: int = 10,
) -> Scenario:
    villages = _villages()
    now = datetime(2026, 6, 1, 8, 0)
    start = now - timedelta(days=days)
    scenario = Scenario(scenario_id=scenario_id, kind=kind, days=days)

    presentations = [p for p, _ in BACKGROUND]
    weights = [w for _, w in BACKGROUND]
    counter = 0

    # ------------------------------------------------------------- background
    for day in range(days):
        # Poisson-ish daily arrivals across the whole district.
        count = sum(1 for _ in range(6) if rng.random() < daily_rate / 6)
        for _ in range(count):
            village = rng.choice(villages)
            counter += 1
            scenario.reports.append(
                SyntheticReport(
                    report_id=f"{scenario_id}-B{counter:05d}",
                    village_id=village["id"],
                    latitude=_jitter(rng, village["lat"], 1.6),
                    longitude=_jitter(rng, village["lon"], 1.6),
                    observed_at=(
                        start + timedelta(days=day, hours=rng.uniform(6, 20))
                    ).isoformat(),
                    symptom_codes=list(rng.choices(presentations, weights=weights, k=1)[0]),
                    species=_species(rng),
                    affected_count=1,
                    deaths_count=1 if rng.random() < 0.012 else 0,
                    herd_size=rng.randint(4, 30),
                    is_outbreak=False,
                )
            )

    if kind == "background":
        return scenario

    # --------------------------------------------------------------- outbreak
    village = rng.choice(villages)
    syndrome = rng.choice(list(OUTBREAK_PROFILES))
    profile = OUTBREAK_PROFILES[syndrome]
    # Start it late enough that a baseline exists before it.
    onset = start + timedelta(days=rng.uniform(days * 0.55, days * 0.75))
    species = _species(rng)

    scenario.outbreak_village = village["id"]
    scenario.outbreak_syndrome = syndrome
    scenario.outbreak_start = onset.isoformat()
    scenario.outbreak_size = outbreak_size

    for index in range(outbreak_size):
        # Accelerating: reports bunch towards the end of the span.
        progress = ((index + 1) / outbreak_size) ** 1.5
        scenario.reports.append(
            SyntheticReport(
                report_id=f"{scenario_id}-O{index + 1:03d}",
                village_id=village["id"],
                latitude=_jitter(rng, village["lat"], 1.8),
                longitude=_jitter(rng, village["lon"], 1.8),
                observed_at=(
                    onset + timedelta(days=progress * outbreak_span_days)
                ).isoformat(),
                symptom_codes=list(rng.choice(profile)),
                species=species,
                affected_count=rng.randint(1, 3),
                deaths_count=1 if rng.random() < 0.14 else 0,
                herd_size=rng.randint(8, 34),
                is_outbreak=True,
            )
        )

    scenario.reports.sort(key=lambda r: r.observed_at)
    return scenario


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenarios", type=int, default=40,
                        help="number of each kind (background and outbreak)")
    parser.add_argument("--days", type=int, default=60)
    parser.add_argument("--daily-rate", type=float, default=2.4,
                        help="mean background reports per day across the district")
    parser.add_argument("--outbreak-size", type=int, default=9)
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--out", type=Path, default=Path("ml/data/synthetic"))
    args = parser.parse_args(argv)

    # Fail fast on a symptom code that no longer exists in the taxonomy.
    for group in (*(p for p, _ in BACKGROUND), *(p for v in OUTBREAK_PROFILES.values() for p in v)):
        for code in group:
            if code not in BY_CODE:
                raise SystemExit(f"Unknown symptom code in generator: {code!r}")

    rng = random.Random(args.seed)
    args.out.mkdir(parents=True, exist_ok=True)

    scenarios: list[Scenario] = []
    for index in range(args.scenarios):
        scenarios.append(generate_scenario(
            f"BG{index + 1:03d}", kind="background", rng=rng,
            days=args.days, daily_rate=args.daily_rate,
        ))
    for index in range(args.scenarios):
        scenarios.append(generate_scenario(
            f"OB{index + 1:03d}", kind="outbreak", rng=rng,
            days=args.days, daily_rate=args.daily_rate,
            outbreak_size=args.outbreak_size,
        ))

    path = args.out / "scenarios.json"
    payload = {
        "generated_at": datetime.utcnow().isoformat(),
        "generator_seed": args.seed,
        "notice": (
            "SYNTHETIC DATA. Generated for detector evaluation under known "
            "conditions. It carries no claim about real-world disease prevalence "
            "and must never be presented as field observation."
        ),
        "parameters": {
            "scenarios_per_kind": args.scenarios,
            "days": args.days,
            "daily_rate": args.daily_rate,
            "outbreak_size": args.outbreak_size,
        },
        "scenarios": [s.to_dict() for s in scenarios],
    }
    path.write_text(json.dumps(payload, indent=1))

    total = sum(len(s.reports) for s in scenarios)
    print(f"Wrote {len(scenarios)} scenarios ({total} reports) to {path}")
    print(f"  background: {args.scenarios}   outbreak: {args.scenarios}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
