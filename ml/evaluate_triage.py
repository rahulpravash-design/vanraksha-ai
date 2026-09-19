#!/usr/bin/env python3
"""Check the triage engine against the clinical vignette set.

What this measures
------------------
Whether the engine reaches the band the project intended for each vignette, and
whether it attaches the handling caution that vignette exists to test. That is a
real property and a useful regression gate: a rule change that quietly stops
escalating downer cows shows up here immediately.

It is **not** a measure of clinical correctness. The expected bands were
authored by the project team, not ratified by a practising veterinarian. Until
they are, a passing run means "the engine does what we intended", not "the
engine is right". The distinction is the whole reason the file says so out loud.

Two error types are reported separately because they cost different things:

* **Under-triage** -- a case that needed a vet was not routed to one. An animal
  may die.
* **Over-triage** -- a routine case was escalated. A veterinary team makes a
  wasted trip, and the queue that urgent cases depend on gets noisier.

    python ml/evaluate_triage.py
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services" / "ai-engine"))

from vanraksha_ai.evaluation import classification_report, escalation_recall  # noqa: E402
from vanraksha_ai.models import Observation, RiskBand, VaccinationStatus  # noqa: E402
from vanraksha_ai.risk import assess  # noqa: E402

ESCALATED = ["priority", "urgent", "emergency"]


def _observation(vignette: dict) -> Observation:
    raw = dict(vignette["observation"])
    status = raw.pop("vaccination_status", "unknown")
    return Observation(
        report_id=vignette["id"],
        reported_at=datetime.utcnow(),
        vaccination_status=VaccinationStatus(status),
        **raw,
    )


def run(vignettes: list[dict]) -> dict:
    rows: list[dict] = []
    under: list[dict] = []
    over: list[dict] = []
    missing_cautions: list[dict] = []

    for vignette in vignettes:
        result = assess(_observation(vignette))
        actual = result.band
        rank = actual.rank

        floor = vignette.get("expect_min")
        ceiling = vignette.get("expect_max")
        ok = True

        if floor and rank < RiskBand(floor).rank:
            ok = False
            under.append({
                "id": vignette["id"], "expected_min": floor,
                "actual": actual.value, "score": round(result.score, 1),
                "why": vignette["why"],
            })
        if ceiling and rank > RiskBand(ceiling).rank:
            ok = False
            over.append({
                "id": vignette["id"], "expected_max": ceiling,
                "actual": actual.value, "score": round(result.score, 1),
                "why": vignette["why"],
            })

        expected_caution = vignette.get("expect_caution")
        caution_ids = [c.caution_id for c in result.cautions]
        if expected_caution and expected_caution not in caution_ids:
            ok = False
            missing_cautions.append({
                "id": vignette["id"], "expected": expected_caution, "attached": caution_ids,
            })

        rows.append({
            "id": vignette["id"],
            "band": actual.value,
            "score": round(result.score, 1),
            "expected_min": floor,
            "expected_max": ceiling,
            "cautions": caution_ids,
            "pass": ok,
        })

    # Escalation recall and precision are computed only over the vignettes that
    # actually make an escalation claim. A vignette saying "at most priority"
    # permits priority, so scoring it as though it demanded "routine" would
    # invent an error; and one saying "at most monitor" is a claim that this
    # must NOT be escalated, which is what precision should be measured on.
    reference: list[str] = []
    predicted: list[str] = []
    for vignette, row in zip(vignettes, rows):
        floor = vignette.get("expect_min")
        ceiling = vignette.get("expect_max")

        if floor and RiskBand(floor).rank >= RiskBand.PRIORITY.rank:
            reference.append(floor)                       # must escalate
        elif ceiling and RiskBand(ceiling).rank < RiskBand.PRIORITY.rank:
            reference.append(ceiling)                     # must not escalate
        else:
            continue                                      # no escalation claim
        predicted.append(row["band"])

    passed = sum(1 for row in rows if row["pass"])
    return {
        "vignettes": len(rows),
        "passed": passed,
        "failed": len(rows) - passed,
        "under_triage": under,
        "over_triage": over,
        "missing_cautions": missing_cautions,
        "escalation": escalation_recall(reference, predicted, ESCALATED),
        "classification": classification_report(reference, predicted),
        "rows": rows,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=Path("ml/triage_vignettes.json"))
    parser.add_argument("--out", type=Path, default=Path("ml/reports/triage_evaluation.json"))
    args = parser.parse_args(argv)

    payload = json.loads(args.data.read_text())
    result = run(payload["vignettes"])
    result["notice"] = payload["notice"]
    result["evaluated_at"] = datetime.utcnow().isoformat()

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2))

    print(f"{'id':>5} {'score':>6} {'band':>10}  {'expected':<22} result")
    print("-" * 68)
    for row in result["rows"]:
        expectation = " / ".join(
            part for part in (
                f">= {row['expected_min']}" if row["expected_min"] else "",
                f"<= {row['expected_max']}" if row["expected_max"] else "",
            ) if part
        )
        print(
            f"{row['id']:>5} {row['score']:>6.1f} {row['band']:>10}  "
            f"{expectation:<22} {'ok' if row['pass'] else 'MISMATCH'}"
        )

    print(f"\n{result['passed']} / {result['vignettes']} vignettes met expectation")
    escalation = result["escalation"]
    print(
        f"  escalation recall    {escalation['escalation_recall']:.2f}  "
        f"({escalation['missed_escalations']} under-triaged)"
    )
    print(
        f"  escalation precision {escalation['escalation_precision']:.2f}  "
        f"({escalation['false_escalations']} over-triaged)"
    )

    if result["under_triage"]:
        print("\nUnder-triage (a case needing a vet was not routed to one):")
        for row in result["under_triage"]:
            print(f"  {row['id']}: got {row['actual']}, expected at least {row['expected_min']}")
            print(f"        {row['why']}")
    if result["over_triage"]:
        print("\nOver-triage (a routine case was escalated):")
        for row in result["over_triage"]:
            print(f"  {row['id']}: got {row['actual']}, expected at most {row['expected_max']}")
            print(f"        {row['why']}")
    if result["missing_cautions"]:
        print("\nMissing handling cautions:")
        for row in result["missing_cautions"]:
            print(f"  {row['id']}: expected {row['expected']}, attached {row['attached']}")

    print(f"\nFull report written to {args.out}")
    print(
        "\nExpected bands are the project's own, pending veterinary review. A pass "
        "means the engine does what was intended, not that the intention is correct."
    )
    return 0 if result["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
