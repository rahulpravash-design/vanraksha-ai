"""Syndromic patterns that carry statutory or public-health consequences.

None of these is a diagnosis, and the engine never presents them as one. They
answer a narrower question that a triage layer *can* answer responsibly:

    "Is this presentation consistent with something where waiting for
     laboratory confirmation would be the wrong first move?"

For a handful of syndromes the answer is yes, because the correct first action
is procedural (do not open the carcass, do not move animals off the premises,
wash a bite wound now) rather than therapeutic. Those are the ones listed here.
Everything else is left to the veterinarian.

Each entry names the syndromic pattern that triggers it, why that pattern
matters, and the handling steps that should happen before a vet arrives.
"""

from __future__ import annotations

from collections.abc import Callable

from ..models import Observation, StatutoryCaution

# A trigger receives the normalised symptom codes and the observation.
Trigger = Callable[[set[str], Observation], bool]


def _bovine(obs: Observation) -> bool:
    return obs.species in ("cattle", "buffalo")


def _small_ruminant(obs: Observation) -> bool:
    return obs.species in ("goat", "sheep")


CAUTION_ANTHRAX = StatutoryCaution(
    caution_id="anthrax_like",
    title="Sudden death with bleeding — handle as a possible anthrax-type event",
    rationale=(
        "Sudden death accompanied by dark, non-clotting blood from the natural "
        "openings is the classical presentation for which carcass handling itself "
        "is the hazard. Opening such a carcass exposes spores to the environment "
        "and to the people doing the opening."
    ),
    actions=(
        "Do NOT open, skin, or cut the carcass, and do not perform a field post-mortem.",
        "Keep people, dogs, and other livestock away from the carcass and the site.",
        "Do not move, sell, slaughter, or consume meat or milk from the affected animal.",
        "Contact the nearest veterinary officer immediately — this is a notifiable event.",
        "Anyone who already handled the carcass should wash exposed skin and seek medical advice.",
    ),
    zoonotic=True,
    notifiable=True,
)

CAUTION_FMD = StatutoryCaution(
    caution_id="fmd_like",
    title="Vesicular signs — apply movement restriction pending veterinary assessment",
    rationale=(
        "Blisters or ulcers in the mouth and around the feet in cloven-hoofed "
        "animals make up the vesicular syndrome. Spread is rapid and largely "
        "driven by animal, vehicle, and footwear movement, so restriction is "
        "worth applying before the cause is confirmed."
    ),
    actions=(
        "Isolate affected animals; stop all movement of livestock on and off the premises.",
        "Do not take animals to markets, fairs, or common grazing until cleared.",
        "Disinfect footwear, hands, and vehicle wheels when leaving the premises.",
        "Report to the veterinary officer — vesicular disease is notifiable.",
        "Record the vaccination date and batch for every affected animal.",
    ),
    zoonotic=False,
    notifiable=True,
)

CAUTION_RABIES = StatutoryCaution(
    caution_id="rabies_like",
    title="Neurological signs with behaviour change — protect handlers first",
    rationale=(
        "Sudden aggression, incoordination, or inability to swallow with profuse "
        "salivation is a presentation where human exposure risk is immediate and "
        "post-exposure treatment is time-critical."
    ),
    actions=(
        "Do not examine the mouth or attempt to drench the animal by hand.",
        "Restrain or confine the animal safely; keep children and other animals away.",
        "Anyone bitten, scratched, or licked on broken skin: wash the wound with soap "
        "under running water for 15 minutes and seek medical care the same day.",
        "Note any history of a dog or wild animal bite in the preceding weeks.",
        "Contact the veterinary officer immediately — this is a notifiable event.",
    ),
    zoonotic=True,
    notifiable=True,
)

CAUTION_ABORTION_STORM = StatutoryCaution(
    caution_id="abortion_cluster",
    title="Multiple abortions — treat aborted material as infectious",
    rationale=(
        "Abortions occurring in more than one animal in a short window raise the "
        "possibility of an infectious reproductive cause. Several of the usual "
        "candidates are transmissible to people handling the foetus, membranes, "
        "or raw milk."
    ),
    actions=(
        "Wear gloves when handling the foetus, membranes, or discharge; wash thoroughly after.",
        "Bury or dispose of aborted material safely; do not leave it for dogs or scavengers.",
        "Isolate the aborting animals and keep their milk out of the raw-milk supply.",
        "Do not consume unboiled milk from the affected herd.",
        "Ask the veterinary officer about serological testing of the herd.",
    ),
    zoonotic=True,
    notifiable=True,
)

CAUTION_NODULAR_SKIN = StatutoryCaution(
    caution_id="nodular_skin",
    title="Nodular skin disease pattern — isolate and control vectors",
    rationale=(
        "Firm skin nodules over the body with fever in bovines follow a vector-borne "
        "spread pattern, so the useful early actions are isolation and biting-fly "
        "control rather than waiting on confirmation."
    ),
    actions=(
        "Isolate affected animals away from the rest of the herd.",
        "Apply vector control — biting flies, mosquitoes, and ticks drive spread.",
        "Stop movement of animals off the premises and to common grazing.",
        "Report to the veterinary officer and confirm the herd's vaccination status.",
    ),
    zoonotic=False,
    notifiable=True,
)

CAUTION_HAEMORRHAGIC_SEPTICAEMIA = StatutoryCaution(
    caution_id="hs_like",
    title="High fever with throat/brisket swelling — a few hours matter",
    rationale=(
        "High fever with oedematous swelling of the throat or brisket and laboured "
        "breathing in bovines is a rapidly fatal presentation, strongly seasonal "
        "around the monsoon, where survival depends on how quickly treatment starts."
    ),
    actions=(
        "Call the veterinary officer now — do not wait for the next visit round.",
        "Separate the animal and keep it calm, shaded, and with water within reach.",
        "Check when the herd was last vaccinated for haemorrhagic septicaemia.",
        "Watch in-contact animals closely for the same signs over the next few days.",
    ),
    zoonotic=False,
    notifiable=True,
)

CAUTION_SMALL_RUMINANT_FEBRILE = StatutoryCaution(
    caution_id="small_ruminant_febrile",
    title="Febrile respiratory-enteric syndrome in small ruminants",
    rationale=(
        "Fever with discharge from the eyes and nose plus diarrhoea in goats or "
        "sheep, especially when several animals are affected, is the pattern that "
        "precedes high flock mortality if it is left to run."
    ),
    actions=(
        "Isolate affected animals from the rest of the flock immediately.",
        "Stop new introductions and do not move animals to markets.",
        "Report to the veterinary officer — this pattern is notifiable in small ruminants.",
        "Provide supportive care: shade, clean water, and fluids as advised.",
    ),
    zoonotic=False,
    notifiable=True,
)

CAUTION_POULTRY_MORTALITY = StatutoryCaution(
    caution_id="poultry_mortality",
    title="Rapid-onset flock mortality — report before disposal",
    rationale=(
        "Sudden death of several birds within a short window is the trigger point "
        "for statutory investigation, and some of the causes carry human health "
        "risk for the people handling the birds."
    ),
    actions=(
        "Do not sell, move, or slaughter birds from the affected shed.",
        "Report to the veterinary officer before disposing of any carcasses.",
        "Restrict entry to the shed; use dedicated footwear inside.",
        "Handlers should wear a mask and gloves and wash hands thoroughly.",
    ),
    zoonotic=True,
    notifiable=True,
)


def _anthrax_trigger(codes: set[str], obs: Observation) -> bool:
    if "bleeding_orifices" in codes and (obs.deaths_count >= 1 or "sudden_death" in codes):
        return True
    # More than one unexplained sudden death in a herd deserves the same caution.
    return "sudden_death" in codes and obs.deaths_count >= 2


def _fmd_trigger(codes: set[str], obs: Observation) -> bool:
    if obs.species not in ("cattle", "buffalo", "goat", "sheep", "pig"):
        return False
    return bool({"oral_lesions", "foot_lesions"} & codes)


def _rabies_trigger(codes: set[str], obs: Observation) -> bool:
    neuro = {"aggression", "circling", "convulsions", "paralysis"} & codes
    if not neuro:
        return False
    # Behaviour change alone is non-specific; salivation or aggression is the
    # combination that makes handler protection the urgent first action.
    return "salivation" in codes or "aggression" in codes


def _abortion_trigger(codes: set[str], obs: Observation) -> bool:
    if "abortion" not in codes:
        return False
    return obs.affected_count >= 2 or obs.in_active_cluster


def _nodular_trigger(codes: set[str], obs: Observation) -> bool:
    return _bovine(obs) and "skin_nodules" in codes


def _hs_trigger(codes: set[str], obs: Observation) -> bool:
    if not _bovine(obs):
        return False
    febrile = "fever" in codes or (obs.temperature_c or 0) >= 40.0
    return febrile and "swelling" in codes and "dyspnoea" in codes


def _small_ruminant_trigger(codes: set[str], obs: Observation) -> bool:
    if not _small_ruminant(obs):
        return False
    febrile = "fever" in codes or (obs.temperature_c or 0) >= 40.5
    discharge = bool({"nasal_discharge", "ocular_discharge"} & codes)
    enteric = bool({"diarrhoea", "bloody_diarrhoea"} & codes)
    return febrile and discharge and (enteric or obs.affected_count >= 3)


def _poultry_trigger(codes: set[str], obs: Observation) -> bool:
    if obs.species != "poultry":
        return False
    return obs.deaths_count >= 5 or ("sudden_death" in codes and obs.affected_count >= 5)


#: Evaluated in order; all matching cautions are attached to the assessment.
CAUTION_RULES: tuple[tuple[Trigger, StatutoryCaution], ...] = (
    (_anthrax_trigger, CAUTION_ANTHRAX),
    (_rabies_trigger, CAUTION_RABIES),
    (_fmd_trigger, CAUTION_FMD),
    (_poultry_trigger, CAUTION_POULTRY_MORTALITY),
    (_hs_trigger, CAUTION_HAEMORRHAGIC_SEPTICAEMIA),
    (_small_ruminant_trigger, CAUTION_SMALL_RUMINANT_FEBRILE),
    (_nodular_trigger, CAUTION_NODULAR_SKIN),
    (_abortion_trigger, CAUTION_ABORTION_STORM),
)

#: Minimum band each caution forces, regardless of the additive score. A
#: single sick animal can score low on herd impact and still need a vet today.
CAUTION_MIN_BAND: dict[str, str] = {
    "anthrax_like": "emergency",
    "rabies_like": "emergency",
    "fmd_like": "urgent",
    "poultry_mortality": "urgent",
    "hs_like": "urgent",
    "small_ruminant_febrile": "urgent",
    "nodular_skin": "priority",
    "abortion_cluster": "priority",
}


def evaluate(codes: set[str], obs: Observation) -> list[StatutoryCaution]:
    """Return every caution whose syndromic pattern this observation matches."""
    return [caution for trigger, caution in CAUTION_RULES if trigger(codes, obs)]
