"""Guardrails for the health assistant.

The assistant sits in front of people who will act on what it says, about
animals that can die, in places where the nearest veterinarian may be hours
away. Two failure modes matter more than anything else:

1. **Naming a diagnosis.** "Your cow has foot-and-mouth disease" is a claim the
   system is not entitled to make from a field report, and it displaces the
   laboratory confirmation that the response actually depends on.
2. **Prescribing.** A dose figure produced by a language model, applied to an
   animal whose weight nobody measured, is a route to a dead animal, a
   residue violation in the milk supply, or both.

Both are blocked at two points: the request is classified before generation,
and the generated text is scanned before it is returned. The second check is
the one that matters, because it holds even when the model is prompted around.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

DISCLAIMER = (
    "This is decision support based on the records in this system, not a diagnosis. "
    "Confirmation and treatment decisions rest with a qualified veterinarian."
)


class RequestVerdict(str, Enum):
    ALLOW = "allow"
    REDIRECT = "redirect"


@dataclass
class SafetyResult:
    verdict: RequestVerdict
    reason: str
    replacement: str | None = None


# Phrasings that are asking the assistant to name a disease.
_DIAGNOSIS_PATTERNS = (
    r"\bwhat (?:disease|illness|infection|condition)\b",
    r"\bwhich (?:disease|illness|infection)\b",
    r"\bdiagnos(?:e|is|ing)\b",
    r"\bdoes (?:my|the|this) \w+ have\b",
    r"\bis (?:it|this|my \w+) (?:fmd|foot and mouth|anthrax|rabies|brucellosis|lsd|hs)\b",
    r"\bconfirm (?:that )?(?:it|this) is\b",
)

# Phrasings that are asking for a treatment or dose.
_PRESCRIPTION_PATTERNS = (
    r"\b(?:what|which) (?:medicine|drug|antibiotic|injection|dose|dosage)\b",
    r"\bhow (?:much|many) (?:ml|mg|cc|tablets?|injections?)\b",
    r"\b(?:prescribe|prescription)\b",
    r"\bshould i (?:give|inject|administer|treat with)\b",
    r"\bcan i (?:give|inject|administer)\b",
    r"\btreat(?:ment)? (?:with|using) \w+",
)

# Output scan: a dose-like quantity, or an explicit instruction to administer.
_DOSE_IN_OUTPUT = re.compile(
    r"\b\d+(?:\.\d+)?\s*(?:mg|ml|cc|g|gm|grams?|milligrams?|millilitres?|milliliters?|iu|units?)\b"
    r"(?:\s*(?:/|per)\s*(?:kg|animal|head|day|dose))?",
    re.IGNORECASE,
)
_ADMINISTER_IN_OUTPUT = re.compile(
    r"\b(?:inject|administer|give|dose)\s+(?:the\s+)?(?:animal\s+)?(?:with\s+)?"
    r"(?:\d|[a-z]+(?:mycin|cillin|azole|xacin|profen|cycline|sulfa))",
    re.IGNORECASE,
)

_REDIRECT_DIAGNOSIS = (
    "I can't name a disease from a field report -- that needs a veterinary examination and, "
    "for most of the conditions that matter here, laboratory confirmation. What I can tell you "
    "is which syndromic pattern these signs fall into, how urgent the case looks against the "
    "triage rules, and what the records show. Ask me about any of those, or request a "
    "veterinary visit from the case screen."
)

_REDIRECT_PRESCRIPTION = (
    "I can't recommend a medicine or a dose. Getting that wrong risks the animal and, for a "
    "lactating or food-producing animal, the milk and meat supply too -- it depends on weight, "
    "pregnancy and lactation status, and withdrawal periods that a veterinarian has to weigh up. "
    "I can flag the case for a vet, show the treatment history already on record, and list the "
    "handling precautions that apply before the vet arrives."
)


def screen_request(text: str) -> SafetyResult:
    """Classify an incoming question before anything is generated."""
    lowered = (text or "").lower()

    for pattern in _PRESCRIPTION_PATTERNS:
        if re.search(pattern, lowered):
            return SafetyResult(
                verdict=RequestVerdict.REDIRECT,
                reason="prescription_request",
                replacement=_REDIRECT_PRESCRIPTION,
            )

    for pattern in _DIAGNOSIS_PATTERNS:
        if re.search(pattern, lowered):
            return SafetyResult(
                verdict=RequestVerdict.REDIRECT,
                reason="diagnosis_request",
                replacement=_REDIRECT_DIAGNOSIS,
            )

    return SafetyResult(verdict=RequestVerdict.ALLOW, reason="ok")


def screen_response(text: str) -> SafetyResult:
    """Scan generated text before it reaches a user.

    Runs regardless of how the text was produced, so a prompt injection that
    talks a language model into emitting a dose still does not reach a farmer.
    """
    if _DOSE_IN_OUTPUT.search(text or ""):
        return SafetyResult(
            verdict=RequestVerdict.REDIRECT,
            reason="dose_in_output",
            replacement=_REDIRECT_PRESCRIPTION,
        )
    if _ADMINISTER_IN_OUTPUT.search(text or ""):
        return SafetyResult(
            verdict=RequestVerdict.REDIRECT,
            reason="administration_instruction_in_output",
            replacement=_REDIRECT_PRESCRIPTION,
        )
    return SafetyResult(verdict=RequestVerdict.ALLOW, reason="ok")


def with_disclaimer(text: str) -> str:
    if DISCLAIMER in text:
        return text
    return f"{text.rstrip()}\n\n{DISCLAIMER}"
