"""Controlled vocabulary for livestock clinical signs.

Field reports arrive as free text in several languages and registers ("not
eating", "poor appetite", "chara nahi kha raha"). Everything downstream --
risk rules, cluster similarity, analytics -- needs a stable code, so the
taxonomy is the single place where surface forms collapse onto one term.

Each term belongs to one or more *syndromic groups*. Syndromic surveillance
groups signs by presentation rather than by diagnosis, which is what lets the
platform flag "a respiratory event is happening in this block" without ever
claiming to know which pathogen is responsible.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Iterable

# --------------------------------------------------------------------------
# Syndromic groups
# --------------------------------------------------------------------------

SYNDROME_RESPIRATORY = "respiratory"
SYNDROME_ENTERIC = "enteric"
SYNDROME_VESICULAR = "vesicular"
SYNDROME_NEUROLOGICAL = "neurological"
SYNDROME_SYSTEMIC = "systemic"
SYNDROME_REPRODUCTIVE = "reproductive"
SYNDROME_UDDER = "udder"
SYNDROME_SKIN = "skin"
SYNDROME_LOCOMOTOR = "locomotor"
SYNDROME_SUDDEN_DEATH = "sudden_death"
SYNDROME_PRODUCTION = "production"

SYNDROME_LABELS: dict[str, str] = {
    SYNDROME_RESPIRATORY: "Respiratory",
    SYNDROME_ENTERIC: "Digestive / enteric",
    SYNDROME_VESICULAR: "Vesicular (mouth / foot lesions)",
    SYNDROME_NEUROLOGICAL: "Neurological",
    SYNDROME_SYSTEMIC: "Systemic / febrile",
    SYNDROME_REPRODUCTIVE: "Reproductive",
    SYNDROME_UDDER: "Udder / mastitis",
    SYNDROME_SKIN: "Skin",
    SYNDROME_LOCOMOTOR: "Locomotor / lameness",
    SYNDROME_SUDDEN_DEATH: "Sudden death",
    SYNDROME_PRODUCTION: "Production drop",
}


@dataclass(frozen=True)
class SymptomTerm:
    """One canonical clinical sign."""

    code: str
    label: str
    syndromes: tuple[str, ...]
    # 0.0 - 1.0. How much this sign alone should worry a triage officer.
    severity_weight: float
    synonyms: tuple[str, ...] = ()
    # Signs a farmer cannot reliably assess without a thermometer or a vet.
    requires_measurement: bool = False


TERMS: tuple[SymptomTerm, ...] = (
    # ---------------------------------------------------------------- systemic
    SymptomTerm(
        code="fever",
        label="Fever",
        syndromes=(SYNDROME_SYSTEMIC,),
        severity_weight=0.55,
        synonyms=(
            "high temperature", "temperature", "hot body", "pyrexia", "bukhar",
            "jwara", "kaaychal", "running temperature", "body hot",
        ),
    ),
    SymptomTerm(
        code="lethargy",
        label="Lethargy / dullness",
        syndromes=(SYNDROME_SYSTEMIC,),
        severity_weight=0.35,
        synonyms=(
            "dull", "dullness", "weak", "weakness", "inactive", "depressed",
            "not moving", "lying down", "sust", "listless", "no energy",
        ),
    ),
    SymptomTerm(
        code="reduced_appetite",
        label="Reduced appetite / anorexia",
        syndromes=(SYNDROME_SYSTEMIC, SYNDROME_ENTERIC),
        severity_weight=0.35,
        synonyms=(
            "not eating", "poor appetite", "reduced food intake", "off feed",
            "anorexia", "refusing feed", "chara nahi kha raha", "no appetite",
            "eating less", "stopped eating",
        ),
    ),
    SymptomTerm(
        code="dehydration",
        label="Dehydration",
        syndromes=(SYNDROME_SYSTEMIC, SYNDROME_ENTERIC),
        severity_weight=0.55,
        synonyms=("sunken eyes", "skin tenting", "dry muzzle", "not drinking"),
    ),
    SymptomTerm(
        code="weight_loss",
        label="Weight loss / emaciation",
        syndromes=(SYNDROME_SYSTEMIC,),
        severity_weight=0.3,
        synonyms=("thin", "emaciated", "losing weight", "wasting", "poor body condition"),
    ),
    # ------------------------------------------------------------- respiratory
    SymptomTerm(
        code="nasal_discharge",
        label="Nasal discharge",
        syndromes=(SYNDROME_RESPIRATORY,),
        severity_weight=0.3,
        synonyms=("runny nose", "snot", "discharge from nose", "nose running"),
    ),
    SymptomTerm(
        code="cough",
        label="Cough",
        syndromes=(SYNDROME_RESPIRATORY,),
        severity_weight=0.35,
        synonyms=("coughing", "khansi", "dry cough", "hacking"),
    ),
    SymptomTerm(
        code="dyspnoea",
        label="Laboured breathing",
        syndromes=(SYNDROME_RESPIRATORY,),
        severity_weight=0.7,
        synonyms=(
            "difficulty breathing", "breathing problem", "panting", "gasping",
            "fast breathing", "open mouth breathing", "respiratory distress",
        ),
    ),
    SymptomTerm(
        code="ocular_discharge",
        label="Ocular discharge",
        syndromes=(SYNDROME_RESPIRATORY, SYNDROME_SYSTEMIC),
        severity_weight=0.25,
        synonyms=("watery eyes", "eye discharge", "tearing", "conjunctivitis"),
    ),
    # ----------------------------------------------------------------- enteric
    SymptomTerm(
        code="diarrhoea",
        label="Diarrhoea",
        syndromes=(SYNDROME_ENTERIC,),
        severity_weight=0.45,
        synonyms=(
            "loose motion", "loose stool", "scours", "watery dung", "dast",
            "loose dung", "watery faeces", "watery feces",
        ),
    ),
    SymptomTerm(
        code="bloody_diarrhoea",
        label="Blood in faeces",
        syndromes=(SYNDROME_ENTERIC,),
        severity_weight=0.75,
        synonyms=("blood in dung", "bloody stool", "dysentery", "blood in stool"),
    ),
    SymptomTerm(
        code="bloat",
        label="Bloat / tympany",
        syndromes=(SYNDROME_ENTERIC,),
        severity_weight=0.7,
        synonyms=("swollen stomach", "distended abdomen", "tympany", "stomach swelling"),
    ),
    SymptomTerm(
        code="salivation",
        label="Excessive salivation / drooling",
        syndromes=(SYNDROME_VESICULAR, SYNDROME_NEUROLOGICAL),
        severity_weight=0.5,
        synonyms=("drooling", "frothing", "foaming at mouth", "saliva", "mouth watering"),
    ),
    # --------------------------------------------------------------- vesicular
    SymptomTerm(
        code="oral_lesions",
        label="Mouth blisters / ulcers",
        syndromes=(SYNDROME_VESICULAR,),
        severity_weight=0.8,
        synonyms=(
            "mouth ulcer", "blister in mouth", "tongue lesion", "vesicles",
            "mouth sores", "tongue ulcer", "muh me chhale",
            # A plural on the LAST token is handled by the matcher, but one in
            # the middle of a phrase needs its own entry: "blisters in mouth"
            # does not contain "blister in mouth". These are the spellings
            # farmers actually type for the vesicular syndrome.
            "blisters in mouth", "blisters in the mouth", "blister in the mouth",
            "mouth blister", "blister on tongue", "blisters on tongue",
        ),
    ),
    SymptomTerm(
        code="foot_lesions",
        label="Foot blisters / lesions between claws",
        syndromes=(SYNDROME_VESICULAR, SYNDROME_LOCOMOTOR),
        severity_weight=0.8,
        synonyms=(
            "hoof lesion", "blister on foot", "sore between hooves",
            "coronary band lesion",
            "blisters on foot", "blisters on feet", "blister on feet",
            "foot blister", "sores between hooves", "blisters between hooves",
            "blister between hooves",
        ),
    ),
    # ------------------------------------------------------------- locomotor
    SymptomTerm(
        code="lameness",
        label="Lameness",
        syndromes=(SYNDROME_LOCOMOTOR,),
        severity_weight=0.4,
        synonyms=("limping", "not walking properly", "leg problem", "langda"),
    ),
    SymptomTerm(
        code="recumbency",
        label="Unable to stand (downer)",
        syndromes=(SYNDROME_LOCOMOTOR, SYNDROME_SYSTEMIC),
        severity_weight=0.85,
        synonyms=("cannot stand", "down cow", "downer", "unable to rise", "collapsed"),
    ),
    # ----------------------------------------------------------- neurological
    SymptomTerm(
        code="circling",
        label="Circling / head pressing",
        syndromes=(SYNDROME_NEUROLOGICAL,),
        severity_weight=0.8,
        synonyms=("head pressing", "walking in circles", "star gazing"),
    ),
    SymptomTerm(
        code="convulsions",
        label="Convulsions / tremors",
        syndromes=(SYNDROME_NEUROLOGICAL,),
        severity_weight=0.85,
        synonyms=("fits", "seizure", "shivering", "tremor", "twitching", "spasms"),
    ),
    SymptomTerm(
        code="aggression",
        label="Sudden aggression / behaviour change",
        syndromes=(SYNDROME_NEUROLOGICAL,),
        severity_weight=0.9,
        synonyms=("biting", "attacking", "restless and violent", "abnormal behaviour", "mad"),
    ),
    SymptomTerm(
        code="paralysis",
        label="Paralysis / incoordination",
        syndromes=(SYNDROME_NEUROLOGICAL, SYNDROME_LOCOMOTOR),
        severity_weight=0.85,
        synonyms=("ataxia", "staggering", "wobbly", "cannot move legs", "incoordination"),
    ),
    # ---------------------------------------------------------- reproductive
    SymptomTerm(
        code="abortion",
        label="Abortion / stillbirth",
        syndromes=(SYNDROME_REPRODUCTIVE,),
        severity_weight=0.75,
        synonyms=("miscarriage", "aborted", "premature calving", "stillborn", "slipped calf"),
    ),
    SymptomTerm(
        code="retained_placenta",
        label="Retained placenta",
        syndromes=(SYNDROME_REPRODUCTIVE,),
        severity_weight=0.45,
        synonyms=("placenta not dropped", "retained foetal membrane", "jer nahi gira"),
    ),
    SymptomTerm(
        code="vaginal_discharge",
        label="Abnormal vaginal discharge",
        syndromes=(SYNDROME_REPRODUCTIVE,),
        severity_weight=0.4,
        synonyms=("foul discharge", "pus discharge", "metritis"),
    ),
    SymptomTerm(
        code="infertility",
        label="Repeat breeding / infertility",
        syndromes=(SYNDROME_REPRODUCTIVE,),
        severity_weight=0.2,
        synonyms=("not conceiving", "repeat breeder", "anoestrus", "not coming to heat"),
    ),
    # ----------------------------------------------------------------- udder
    SymptomTerm(
        code="udder_swelling",
        label="Udder swelling / hardness",
        syndromes=(SYNDROME_UDDER,),
        severity_weight=0.5,
        synonyms=("swollen udder", "hard udder", "hot udder", "mastitis", "than sujan"),
    ),
    SymptomTerm(
        code="abnormal_milk",
        label="Abnormal milk (clots / blood / watery)",
        syndromes=(SYNDROME_UDDER,),
        severity_weight=0.5,
        synonyms=("clots in milk", "blood in milk", "watery milk", "flakes in milk"),
    ),
    SymptomTerm(
        code="milk_drop",
        label="Sudden milk yield drop",
        syndromes=(SYNDROME_PRODUCTION, SYNDROME_UDDER),
        severity_weight=0.3,
        synonyms=("less milk", "milk reduced", "drop in milk", "yield fall", "doodh kam"),
    ),
    # ------------------------------------------------------------------ skin
    SymptomTerm(
        code="skin_nodules",
        label="Skin nodules / lumps",
        syndromes=(SYNDROME_SKIN,),
        severity_weight=0.7,
        synonyms=("lumps on skin", "nodules", "bumps on body", "skin knots", "gaanth"),
    ),
    SymptomTerm(
        code="skin_lesions",
        label="Skin wounds / scabs",
        syndromes=(SYNDROME_SKIN,),
        severity_weight=0.3,
        synonyms=("sores", "scabs", "wounds", "crusts", "hair loss", "mange"),
    ),
    SymptomTerm(
        code="swelling",
        label="Localised swelling / oedema",
        syndromes=(SYNDROME_SYSTEMIC, SYNDROME_SKIN),
        severity_weight=0.5,
        synonyms=("swollen", "oedema", "edema", "puffy", "swelling on neck", "brisket swelling"),
    ),
    SymptomTerm(
        code="ectoparasites",
        label="Ticks / lice infestation",
        syndromes=(SYNDROME_SKIN,),
        severity_weight=0.2,
        synonyms=("ticks", "lice", "mites", "fleas", "kilni"),
    ),
    # ----------------------------------------------------------- sudden death
    SymptomTerm(
        code="sudden_death",
        label="Sudden death without prior signs",
        syndromes=(SYNDROME_SUDDEN_DEATH, SYNDROME_SYSTEMIC),
        severity_weight=1.0,
        synonyms=("found dead", "died suddenly", "unexpected death", "died without symptoms"),
    ),
    SymptomTerm(
        code="bleeding_orifices",
        label="Bleeding from natural openings",
        syndromes=(SYNDROME_SUDDEN_DEATH, SYNDROME_SYSTEMIC),
        severity_weight=1.0,
        synonyms=(
            "blood from nose", "bleeding from mouth", "blood from anus",
            "tarry blood", "unclotted blood", "bleeding from orifices",
        ),
    ),
)

BY_CODE: dict[str, SymptomTerm] = {t.code: t for t in TERMS}

# Longest surface forms first so "blood in dung" wins over "blood".
_SURFACE_FORMS: list[tuple[str, str]] = sorted(
    [(t.label.lower(), t.code) for t in TERMS]
    + [(t.code.replace("_", " "), t.code) for t in TERMS]
    + [(s, t.code) for t in TERMS for s in t.synonyms],
    key=lambda pair: len(pair[0]),
    reverse=True,
)

_NEGATION_CUES = (
    "no ", "not ", "without ", "denies ", "absent ", "nahi ", "never ",
    "free of ", "ruled out ",
)


def _fold(text: str) -> str:
    """Lowercase, strip accents, squeeze punctuation into single spaces."""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.lower()
    text = re.sub(r"[^a-z0-9ऀ-ൿ]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _is_negated(haystack: str, start: int) -> bool:
    """True when a negation cue sits in the ~24 characters before a match."""
    window = haystack[max(0, start - 24):start]
    return any(cue in window for cue in _NEGATION_CUES)


def _match_end(haystack: str, end: int) -> int | None:
    """Where a surface-form match ends, allowing a plural on the last token.

    The taxonomy lists singulars, but field text is overwhelmingly plural --
    "mouth ulcers", "blisters", "tremors". Requiring a token boundary right
    after the singular rejects every one of those, so a trailing "s" or "es"
    is accepted as part of the match. Returns ``None`` when the surface form
    ends mid-token, which is what stops "cough" matching "coughdrop".
    """
    for candidate in (end, end + 1, end + 2):
        if candidate > len(haystack):
            break
        if candidate > end and haystack[end:candidate] not in ("s", "es"):
            continue
        if candidate == len(haystack) or haystack[candidate] == " ":
            return candidate
    return None


@dataclass
class NormalisationResult:
    codes: list[str] = field(default_factory=list)
    unmatched: list[str] = field(default_factory=list)
    negated: list[str] = field(default_factory=list)

    @property
    def syndromes(self) -> list[str]:
        return syndromes_for(self.codes)


def normalise(raw_symptoms: Iterable[str]) -> NormalisationResult:
    """Map free-text symptom phrases onto taxonomy codes.

    Handles the three things field text actually does: synonyms, several signs
    crammed into one string ("fever and cough"), and negation ("no fever").
    Anything unrecognised is preserved in ``unmatched`` rather than silently
    dropped -- unmatched phrases are a signal that the taxonomy needs a new
    synonym, and they are surfaced to veterinary reviewers for exactly that.
    """
    result = NormalisationResult()
    seen: set[str] = set()

    for raw in raw_symptoms:
        if not raw or not raw.strip():
            continue
        folded = _fold(raw)
        if not folded:
            continue

        # Exact code match short-circuits everything (API clients send codes).
        if raw.strip() in BY_CODE:
            if raw.strip() not in seen:
                seen.add(raw.strip())
                result.codes.append(raw.strip())
            continue

        working = folded
        matched_any = False
        for surface, code in _SURFACE_FORMS:
            idx = working.find(surface)
            if idx == -1:
                continue
            # Require token boundaries so "cough" does not match "coughdrop".
            if not (idx == 0 or working[idx - 1] == " "):
                continue
            after = _match_end(working, idx + len(surface))
            if after is None:
                continue

            matched_any = True
            if _is_negated(working, idx):
                if code not in result.negated:
                    result.negated.append(code)
            elif code not in seen:
                seen.add(code)
                result.codes.append(code)
            # Blank the span so overlapping surface forms do not double-count.
            working = working[:idx] + " " * (after - idx) + working[after:]

        if not matched_any:
            result.unmatched.append(raw.strip())

    return result


def syndromes_for(codes: Iterable[str]) -> list[str]:
    """Distinct syndromic groups covered by a set of symptom codes."""
    out: list[str] = []
    for code in codes:
        term = BY_CODE.get(code)
        if not term:
            continue
        for syndrome in term.syndromes:
            if syndrome not in out:
                out.append(syndrome)
    return out


def dominant_syndrome(codes: Iterable[str]) -> str | None:
    """The syndromic group carrying the most clinical weight in this report."""
    scores: dict[str, float] = {}
    for code in codes:
        term = BY_CODE.get(code)
        if not term:
            continue
        for syndrome in term.syndromes:
            scores[syndrome] = scores.get(syndrome, 0.0) + term.severity_weight
    if not scores:
        return None
    return max(scores.items(), key=lambda kv: (kv[1], kv[0]))[0]


def label_for(code: str) -> str:
    term = BY_CODE.get(code)
    return term.label if term else code.replace("_", " ").title()


def severity_of(codes: Iterable[str]) -> float:
    """Highest single-sign severity weight present, 0.0 when nothing matched."""
    weights = [BY_CODE[c].severity_weight for c in codes if c in BY_CODE]
    return max(weights) if weights else 0.0
