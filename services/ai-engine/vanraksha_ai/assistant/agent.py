"""A grounded health assistant.

The design rule is that the assistant may *arrange* facts but never *invent*
them. Every sentence it produces traces to a record passed in as context. That
rule is what makes it useful to a veterinary officer rather than a novelty:
"six reports this month against two last month, four of them respiratory" is
worth reading; a fluent paragraph that might be made up is not.

A language model is optional and strictly downstream. Without one the assistant
answers from deterministic templates over the same context. With one, the model
is handed a context block it is instructed not to go beyond, and whatever it
returns is still run through the output guardrails and the grounding check
before anyone sees it. The feature therefore degrades to "less fluent" when the
API key is missing or the provider is down, never to "unavailable" and never to
"unverified".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol, Sequence

from ..taxonomy import SYNDROME_LABELS, label_for
from ..trends import describe_trend
from .safety import RequestVerdict, screen_request, screen_response, with_disclaimer

ASSISTANT_VERSION = "assistant/1.0.0"


class LanguageModel(Protocol):
    """Minimal port for an LLM. Anything matching this shape can be injected."""

    def complete(self, system: str, user: str) -> str: ...


@dataclass
class AssistantContext:
    """Everything the assistant is allowed to talk about, and nothing else."""

    scope_label: str
    period_label: str = "the last 30 days"
    report_count: int = 0
    previous_period_count: int | None = None
    animal_count: int = 0
    death_count: int = 0
    syndrome_counts: dict[str, int] = field(default_factory=dict)
    top_symptoms: list[tuple[str, int]] = field(default_factory=list)
    band_counts: dict[str, int] = field(default_factory=dict)
    active_clusters: list[dict[str, Any]] = field(default_factory=list)
    open_cases: int = 0
    overdue_vaccinations: int = 0
    weekly_series: list[float] = field(default_factory=list)
    generated_at: datetime = field(default_factory=datetime.utcnow)

    def as_prompt_block(self) -> str:
        """Render the context the way it is handed to a language model."""
        lines = [
            f"scope: {self.scope_label}",
            f"period: {self.period_label}",
            f"reports: {self.report_count}",
        ]
        if self.previous_period_count is not None:
            lines.append(f"reports_previous_period: {self.previous_period_count}")
        lines += [
            f"animals_affected: {self.animal_count}",
            f"deaths: {self.death_count}",
            f"open_cases: {self.open_cases}",
            f"overdue_vaccinations: {self.overdue_vaccinations}",
        ]
        if self.syndrome_counts:
            joined = ", ".join(f"{k}={v}" for k, v in self.syndrome_counts.items())
            lines.append(f"syndrome_counts: {joined}")
        if self.top_symptoms:
            joined = ", ".join(f"{code}={n}" for code, n in self.top_symptoms)
            lines.append(f"top_symptoms: {joined}")
        if self.band_counts:
            joined = ", ".join(f"{k}={v}" for k, v in self.band_counts.items())
            lines.append(f"triage_bands: {joined}")
        for cluster in self.active_clusters:
            lines.append(
                f"active_cluster: id={cluster.get('cluster_id')} "
                f"reports={cluster.get('report_count')} "
                f"severity={cluster.get('severity_score')} "
                f"syndrome={cluster.get('dominant_syndrome')}"
            )
        if self.weekly_series:
            lines.append(
                "weekly_report_counts: " + ", ".join(str(int(v)) for v in self.weekly_series)
            )
        return "\n".join(lines)


SYSTEM_PROMPT = """You are the reporting assistant for a livestock health surveillance platform.

Rules, in order of precedence:
1. Use only the facts in the CONTEXT block. If the context does not contain
   something, say that it is not in the records. Never estimate or fill gaps.
2. Never name a disease as the cause. Describe syndromic patterns instead
   ("a respiratory pattern"), and say that confirmation requires a veterinarian.
3. Never recommend a medicine, a dose, or a route of administration.
4. Lead with the number that changed. Be concise: at most six sentences.
5. Write for a district veterinary officer: plain, specific, no marketing tone.
"""


class HealthAssistant:
    version = ASSISTANT_VERSION

    def __init__(self, model: LanguageModel | None = None) -> None:
        self.model = model

    def summarise(self, context: AssistantContext) -> dict[str, Any]:
        """A situation summary for a scope. Always grounded, LLM optional."""
        deterministic = self._template_summary(context)

        if self.model is None:
            return self._package(deterministic, context, source="template")

        try:
            raw = self.model.complete(
                SYSTEM_PROMPT,
                f"CONTEXT\n{context.as_prompt_block()}\n\n"
                f"Task: summarise the situation for {context.scope_label} over "
                f"{context.period_label}.",
            )
        except Exception:
            # A provider outage must not take the feature down.
            return self._package(deterministic, context, source="template_fallback")

        checked = screen_response(raw)
        if checked.verdict is RequestVerdict.REDIRECT:
            return self._package(deterministic, context, source="template_guardrail")
        if not self._is_grounded(raw, context):
            return self._package(deterministic, context, source="template_ungrounded")

        return self._package(raw.strip(), context, source="model")

    def answer(self, question: str, context: AssistantContext) -> dict[str, Any]:
        """Answer a question about a scope, refusing what it must refuse."""
        screened = screen_request(question)
        if screened.verdict is RequestVerdict.REDIRECT:
            return {
                "answer": with_disclaimer(screened.replacement or ""),
                "source": "guardrail",
                "guardrail": screened.reason,
                "grounded_in": context.scope_label,
                "assistant_version": ASSISTANT_VERSION,
            }

        result = self.summarise(context)
        result["question"] = question
        return result

    # ---------------------------------------------------------------- internals

    def _package(
        self, text: str, context: AssistantContext, *, source: str
    ) -> dict[str, Any]:
        return {
            "answer": with_disclaimer(text),
            "source": source,
            "grounded_in": context.scope_label,
            "context_digest": context.as_prompt_block(),
            "assistant_version": ASSISTANT_VERSION,
        }

    @staticmethod
    def _is_grounded(text: str, context: AssistantContext) -> bool:
        """Reject model output that introduces numbers the context never had.

        A blunt check, and deliberately so: the numbers are the part of a
        summary that gets quoted in a meeting, and a hallucinated count is worse
        than a plainer sentence.
        """
        import re

        known = {
            str(context.report_count), str(context.animal_count),
            str(context.death_count), str(context.open_cases),
            str(context.overdue_vaccinations),
        }
        if context.previous_period_count is not None:
            known.add(str(context.previous_period_count))
        known |= {str(v) for v in context.syndrome_counts.values()}
        known |= {str(n) for _, n in context.top_symptoms}
        known |= {str(v) for v in context.band_counts.values()}
        known |= {str(int(v)) for v in context.weekly_series}
        for cluster in context.active_clusters:
            known |= {str(cluster.get("report_count")), str(cluster.get("severity_score"))}

        for number in re.findall(r"\b\d+\b", text):
            # Small integers are ordinary prose ("the last 7 days"); anything
            # larger has to come from the record set.
            if int(number) > 1 and number not in known:
                return False
        return True

    @staticmethod
    def _template_summary(ctx: AssistantContext) -> str:
        if ctx.report_count == 0:
            return (
                f"No health reports were filed for {ctx.scope_label} during {ctx.period_label}. "
                f"{ctx.overdue_vaccinations} vaccination(s) are showing as overdue. "
                "An absence of reports is not the same as an absence of disease -- it is worth "
                "confirming that field workers in this area are able to submit."
            )

        sentences: list[str] = []

        change = ""
        if ctx.previous_period_count is not None:
            if ctx.previous_period_count == 0:
                change = " against none in the previous period"
            else:
                delta = ctx.report_count - ctx.previous_period_count
                direction = "up from" if delta > 0 else "down from" if delta < 0 else "level with"
                change = f", {direction} {ctx.previous_period_count} in the previous period"
        sentences.append(
            f"{ctx.scope_label} recorded {ctx.report_count} health report(s) during "
            f"{ctx.period_label}{change}, covering {ctx.animal_count} animal(s)."
        )

        if ctx.syndrome_counts:
            top = max(ctx.syndrome_counts.items(), key=lambda kv: (kv[1], kv[0]))
            label = SYNDROME_LABELS.get(top[0], top[0]).lower()
            sentences.append(f"The most frequent presentation is {label} ({top[1]} report(s)).")

        if ctx.top_symptoms:
            signs = ", ".join(label_for(code).lower() for code, _ in ctx.top_symptoms[:3])
            sentences.append(f"The signs reported most often are {signs}.")

        if ctx.death_count:
            sentences.append(f"{ctx.death_count} death(s) were recorded in this period.")

        if ctx.active_clusters:
            worst = max(ctx.active_clusters, key=lambda c: c.get("severity_score", 0))
            sentences.append(
                f"{len(ctx.active_clusters)} cluster(s) are currently active; the most severe is "
                f"{worst.get('cluster_id')} with {worst.get('report_count')} report(s)."
            )

        escalated = sum(
            ctx.band_counts.get(band, 0) for band in ("priority", "urgent", "emergency")
        )
        if escalated:
            sentences.append(
                f"{escalated} report(s) were triaged at priority level or above, and "
                f"{ctx.open_cases} case(s) remain open."
            )

        if len(ctx.weekly_series) >= 3:
            sentences.append(f"Week-on-week reporting is {describe_trend(ctx.weekly_series)}.")

        if ctx.overdue_vaccinations:
            sentences.append(
                f"{ctx.overdue_vaccinations} vaccination(s) are overdue in this scope."
            )

        return " ".join(sentences)


def build_context(
    *,
    scope_label: str,
    reports: Sequence[dict[str, Any]],
    period_label: str = "the last 30 days",
    previous_period_count: int | None = None,
    active_clusters: Sequence[dict[str, Any]] = (),
    open_cases: int = 0,
    overdue_vaccinations: int = 0,
    weekly_series: Sequence[float] = (),
) -> AssistantContext:
    """Aggregate raw report dicts into a context object."""
    syndrome_counts: dict[str, int] = {}
    symptom_counts: dict[str, int] = {}
    band_counts: dict[str, int] = {}
    animals = 0
    deaths = 0

    for report in reports:
        animals += int(report.get("affected_count") or 0)
        deaths += int(report.get("deaths_count") or 0)
        band = report.get("risk_band")
        if band:
            band_counts[band] = band_counts.get(band, 0) + 1
        for syndrome in report.get("syndromes") or []:
            syndrome_counts[syndrome] = syndrome_counts.get(syndrome, 0) + 1
        for code in report.get("symptom_codes") or []:
            symptom_counts[code] = symptom_counts.get(code, 0) + 1

    return AssistantContext(
        scope_label=scope_label,
        period_label=period_label,
        report_count=len(reports),
        previous_period_count=previous_period_count,
        animal_count=animals,
        death_count=deaths,
        syndrome_counts=dict(sorted(syndrome_counts.items(), key=lambda kv: (-kv[1], kv[0]))),
        top_symptoms=sorted(symptom_counts.items(), key=lambda kv: (-kv[1], kv[0]))[:5],
        band_counts=band_counts,
        active_clusters=list(active_clusters),
        open_cases=open_cases,
        overdue_vaccinations=overdue_vaccinations,
        weekly_series=list(weekly_series),
    )
