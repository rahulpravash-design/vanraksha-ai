#!/usr/bin/env python3
"""Measure cluster-detection behaviour against scenarios with known answers.

What this does and does not establish
-------------------------------------
It establishes how the detector behaves **under known conditions**: given
background-only data, how often does it raise a cluster anyway; given an
injected event, how often does it find it, and how long does it take.

It establishes nothing about real-world performance. The data is synthetic, so
these numbers describe the detector's response to the generator's assumptions,
not to a real district. They are useful for exactly two things: choosing
parameters, and noticing when a change makes detection worse.

The metrics reported are the ones that matter operationally:

* **False alert rate** -- clusters raised per background scenario. Every one of
  these costs a veterinary team a field visit that finds nothing, and a few of
  them teach an officer to ignore the system.
* **Detection rate** -- share of injected events found at all.
* **Detection delay** -- hours from the event's first report to the sweep that
  would first have caught it. A detector that is perfectly accurate three weeks
  late has not helped anyone.

    python ml/evaluate_detector.py --sweep
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services" / "ai-engine"))

from vanraksha_ai.clustering import ClusterConfig, ClusterPoint, detect_clusters  # noqa: E402
from vanraksha_ai.evaluation import alert_quality, detection_delay_hours  # noqa: E402
from vanraksha_ai.models import SPECIES_GROUP  # noqa: E402

#: How often surveillance runs in deployment. Detection delay is quantised to
#: this, because a cluster cannot be found before the next sweep looks for it.
SWEEP_INTERVAL_HOURS = 24
#: Trailing window each sweep considers.
SWEEP_WINDOW_DAYS = 21


def _points(reports: list[dict]) -> list[ClusterPoint]:
    return [
        ClusterPoint(
            report_id=r["report_id"],
            latitude=r["latitude"],
            longitude=r["longitude"],
            observed_at=datetime.fromisoformat(r["observed_at"]),
            symptom_codes=list(r["symptom_codes"]),
            species=r["species"],
            species_group=SPECIES_GROUP.get(r["species"], r["species"]),
            village_id=r["village_id"],
            affected_count=r["affected_count"],
            deaths_count=r["deaths_count"],
        )
        for r in reports
    ]


def _is_the_event(cluster, outbreak_ids: set[str]) -> bool:
    """A cluster counts as the event when most of it is the event.

    A cluster that swept in two unrelated background reports alongside eight
    outbreak ones has still found the event; one built mostly from background
    noise that happens to touch it has not.
    """
    if not cluster.point_ids:
        return False
    overlap = sum(1 for pid in cluster.point_ids if pid in outbreak_ids)
    return overlap >= 3 and overlap / len(cluster.point_ids) >= 0.5


def evaluate(scenarios: list[dict], config: ClusterConfig) -> dict:
    background_alerts = 0
    background_scenarios = 0
    confirmed = 0
    missed = 0
    false_in_outbreak = 0

    first_report_epochs: list[float] = []
    detected_epochs: list[float] = []

    for scenario in scenarios:
        reports = scenario["reports"]
        outbreak_ids = {r["report_id"] for r in reports if r["is_outbreak"]}

        if scenario["kind"] == "background":
            background_scenarios += 1
            # One sweep over the most recent window is the realistic unit.
            latest = max(datetime.fromisoformat(r["observed_at"]) for r in reports)
            window = [
                r for r in reports
                if datetime.fromisoformat(r["observed_at"])
                >= latest - timedelta(days=SWEEP_WINDOW_DAYS)
            ]
            background_alerts += len(detect_clusters(_points(window), config))
            continue

        # ------------------------------------------------- outbreak scenario
        onset = datetime.fromisoformat(scenario["outbreak_start"])
        event_first = min(
            datetime.fromisoformat(r["observed_at"]) for r in reports if r["is_outbreak"]
        )

        # Replay the sweeps that would actually have run, and record the first
        # one that catches it -- not whether it is visible in hindsight.
        found_at: datetime | None = None
        spurious = 0
        cursor = onset
        horizon = max(datetime.fromisoformat(r["observed_at"]) for r in reports)

        while cursor <= horizon + timedelta(days=2):
            window = [
                r for r in reports
                if cursor - timedelta(days=SWEEP_WINDOW_DAYS)
                <= datetime.fromisoformat(r["observed_at"]) <= cursor
            ]
            clusters = detect_clusters(_points(window), config)
            hits = [c for c in clusters if _is_the_event(c, outbreak_ids)]
            spurious = max(spurious, len(clusters) - len(hits))
            if hits and found_at is None:
                found_at = cursor
                break
            cursor += timedelta(hours=SWEEP_INTERVAL_HOURS)

        false_in_outbreak += spurious
        if found_at is not None:
            confirmed += 1
            first_report_epochs.append(event_first.timestamp())
            detected_epochs.append(found_at.timestamp())
        else:
            missed += 1

    quality = alert_quality(
        confirmed=confirmed,
        rejected=background_alerts + false_in_outbreak,
        missed_events=missed,
    )
    delay = detection_delay_hours(first_report_epochs, detected_epochs)

    return {
        "config": {
            "radius_km": config.radius_km,
            "window_hours": config.window_hours,
            "min_reports": config.min_reports,
            "min_similarity": config.min_similarity,
        },
        "background_scenarios": background_scenarios,
        "false_alerts_on_background": background_alerts,
        "false_alerts_per_background_scenario": round(
            background_alerts / background_scenarios, 3
        ) if background_scenarios else None,
        "outbreaks_detected": confirmed,
        "outbreaks_missed": missed,
        "detection_rate": round(confirmed / (confirmed + missed), 3) if (confirmed + missed) else None,
        "alert_quality": quality,
        "detection_delay": delay,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=Path("ml/data/synthetic/scenarios.json"))
    parser.add_argument("--out", type=Path, default=Path("ml/reports/detector_evaluation.json"))
    parser.add_argument("--sweep", action="store_true",
                        help="evaluate a grid of parameters instead of the default only")
    args = parser.parse_args(argv)

    if not args.data.exists():
        raise SystemExit(
            f"{args.data} not found. Run ml/generate_dataset.py first."
        )

    payload = json.loads(args.data.read_text())
    scenarios = payload["scenarios"]

    configs = [ClusterConfig()]
    if args.sweep:
        configs = [
            ClusterConfig(radius_km=r, window_hours=w, min_reports=m)
            for r in (3.0, 5.0, 8.0)
            for w in (120.0, 168.0, 240.0)
            for m in (3, 4)
        ]

    results = [evaluate(scenarios, config) for config in configs]

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps({
        "evaluated_at": datetime.utcnow().isoformat(),
        "data": str(args.data),
        "generator_seed": payload.get("generator_seed"),
        "notice": payload.get("notice"),
        "results": results,
    }, indent=2))

    header = f"{'radius':>7} {'window':>7} {'min':>4} | {'detect':>7} {'delay h':>8} {'false/bg':>9} {'precision':>10}"
    print(header)
    print("-" * len(header))
    for result in results:
        config = result["config"]
        print(
            f"{config['radius_km']:>7.1f} {config['window_hours']:>7.0f} "
            f"{config['min_reports']:>4} | "
            f"{(result['detection_rate'] or 0):>7.2f} "
            f"{result['detection_delay']['median_hours']:>8.1f} "
            f"{(result['false_alerts_per_background_scenario'] or 0):>9.2f} "
            f"{result['alert_quality']['alert_precision']:>10.2f}"
        )

    print(f"\nFull report written to {args.out}")
    print(
        "\nThese numbers describe detector behaviour on SYNTHETIC scenarios. "
        "They say nothing about real-world performance."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
