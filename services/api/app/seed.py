"""Synthetic demonstration dataset.

**Everything this module generates is synthetic.** It is shaped to be
*plausible* -- seasonal background reporting, a realistic mix of syndromes, an
injected outbreak with a believable growth curve -- so that the workflow can be
exercised end to end. It is not drawn from real herds and it carries no claim
about real-world disease prevalence. Nothing measured against this data says
anything about how the system would perform in the field; see
`docs/06-data/synthetic-data.md` for what it can and cannot be used for.

Determinism is on purpose: the same seed produces the same dataset, so a demo
is reproducible and a regression in detection shows up as a changed cluster
count rather than as noise.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import (
    Animal,
    Farm,
    HealthReport,
    Role,
    User,
    Vaccination,
    Village,
    utcnow,
)
from .security import hash_password
from .services.triage import assess_report

DEFAULT_PASSWORD = "VanrakshaDemo2026!"

# A block in a plausible South Indian district. Coordinates are real places so
# that the map renders sensibly; the livestock data attached to them is not.
VILLAGES = [
    ("Hoskote",      "Hoskote",   13.0707, 77.7982, 1850),
    ("Sulibele",     "Hoskote",   13.1667, 77.8500, 1240),
    ("Jadigenahalli","Hoskote",   13.0333, 77.8667, 980),
    ("Anugondanahalli","Hoskote", 12.9833, 77.8833, 760),
    ("Devanahalli",  "Devanahalli", 13.2437, 77.7128, 1620),
    ("Vijayapura",   "Devanahalli", 13.3167, 77.8000, 1105),
    ("Channarayapatna","Devanahalli", 13.2000, 77.6500, 890),
    ("Nelamangala",  "Nelamangala", 13.0997, 77.3939, 1430),
]
DISTRICT = "Bengaluru Rural"
STATE = "Karnataka"

SPECIES_MIX = (
    ("cattle", 0.44), ("buffalo", 0.18), ("goat", 0.24),
    ("sheep", 0.09), ("poultry", 0.05),
)

BREEDS = {
    "cattle": ["Hallikar", "Deoni", "Holstein Friesian cross", "Jersey cross", "Gir"],
    "buffalo": ["Murrah", "Surti", "Local"],
    "goat": ["Osmanabadi", "Sirohi", "Local"],
    "sheep": ["Deccani", "Bannur", "Local"],
    "poultry": ["Giriraja", "Broiler", "Desi"],
}

# Background presentations with their rough relative frequency. Weighted so the
# everyday complaints dominate, as they do in practice.
BACKGROUND_PRESENTATIONS = [
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
    (["abortion"], 2),
]

VACCINES = [
    ("Foot and Mouth Disease", 180),
    ("Haemorrhagic Septicaemia", 365),
    ("Black Quarter", 365),
    ("Peste des Petits Ruminants", 1095),
    ("Brucellosis", 365),
]


def _weighted_species(rng: random.Random) -> str:
    roll = rng.random()
    cumulative = 0.0
    for species, share in SPECIES_MIX:
        cumulative += share
        if roll <= cumulative:
            return species
    return "cattle"


def _jitter(rng: random.Random, value: float, spread: float = 0.02) -> float:
    return round(value + rng.uniform(-spread, spread), 6)


def seed(db: Session, *, seed_value: int = 2026, days: int = 90) -> dict:
    """Populate an empty database with a reproducible synthetic district."""
    if db.scalar(select(User).limit(1)) is not None:
        return {"status": "skipped", "reason": "database already contains data"}

    rng = random.Random(seed_value)
    now = utcnow()
    summary: dict = {"password": DEFAULT_PASSWORD, "accounts": []}

    # ------------------------------------------------------------- geography
    villages: list[Village] = []
    for name, block, lat, lon, population in VILLAGES:
        village = Village(
            name=name, block=block, district=DISTRICT, state=STATE,
            latitude=lat, longitude=lon, livestock_population=population,
        )
        db.add(village)
        villages.append(village)
    db.flush()

    # ----------------------------------------------------------------- staff
    staff_spec = [
        ("vet.hoskote@example.org", "Dr. A. Ramesh", Role.VETERINARIAN, "Hoskote"),
        ("vet.devanahalli@example.org", "Dr. S. Lakshmi", Role.VETERINARIAN, "Devanahalli"),
        ("field.hoskote@example.org", "M. Nagaraj", Role.FIELD_WORKER, "Hoskote"),
        ("block.hoskote@example.org", "Block Officer, Hoskote", Role.BLOCK_ADMIN, "Hoskote"),
        ("district@example.org", "District Officer", Role.DISTRICT_ADMIN, None),
    ]
    staff: dict[str, User] = {}
    for email, full_name, role, block in staff_spec:
        user = User(
            email=email, hashed_password=hash_password(DEFAULT_PASSWORD),
            full_name=full_name, role=role, block=block, district=DISTRICT,
        )
        db.add(user)
        staff[email] = user
        summary["accounts"].append({"email": email, "role": role.value})
    db.flush()

    # --------------------------------------------------------------- farmers
    farms: list[Farm] = []
    animals: list[Animal] = []

    for index in range(28):
        village = rng.choice(villages)
        email = f"farmer{index + 1}@example.org"
        farmer = User(
            email=email, hashed_password=hash_password(DEFAULT_PASSWORD),
            full_name=f"Farmer {index + 1}", role=Role.FARMER,
            village_id=village.id, block=village.block, district=DISTRICT,
            language=rng.choice(["en", "kn", "hi"]),
        )
        db.add(farmer)
        db.flush()
        if index == 0:
            summary["accounts"].append({"email": email, "role": "farmer"})

        farm = Farm(
            name=f"{farmer.full_name}'s holding",
            owner_id=farmer.id, village_id=village.id,
            latitude=_jitter(rng, village.latitude),
            longitude=_jitter(rng, village.longitude),
        )
        db.add(farm)
        db.flush()
        farms.append(farm)

        for tag_index in range(rng.randint(3, 14)):
            species = _weighted_species(rng)
            age_months = rng.randint(2, 132)
            female = rng.random() < 0.78
            animal = Animal(
                tag=f"{village.name[:3].upper()}-{index + 1:02d}-{tag_index + 1:02d}",
                species=species,
                breed=rng.choice(BREEDS[species]),
                sex="female" if female else "male",
                date_of_birth=now - timedelta(days=age_months * 30),
                farm_id=farm.id,
                is_pregnant=female and species in ("cattle", "buffalo") and rng.random() < 0.22,
                is_lactating=female and species in ("cattle", "buffalo") and rng.random() < 0.45,
            )
            db.add(animal)
            animals.append(animal)
    db.flush()

    # ---------------------------------------------------------- vaccinations
    for animal in animals:
        if rng.random() < 0.18:
            continue  # never vaccinated
        vaccine, interval = rng.choice(VACCINES)
        # A deliberate share are overdue, so coverage dashboards have something
        # real to show and the risk engine's prevention rule is exercised.
        administered = now - timedelta(days=rng.randint(30, interval + 200))
        db.add(
            Vaccination(
                animal_id=animal.id,
                vaccine=vaccine,
                administered_on=administered,
                next_due_on=administered + timedelta(days=interval),
                batch_number=f"B{rng.randint(10000, 99999)}",
                administered_by=staff["field.hoskote@example.org"].id,
            )
        )
    db.flush()

    # ------------------------------------------------------- background load
    reports: list[HealthReport] = []
    by_village: dict[str, list[Animal]] = {}
    for farm in farms:
        by_village.setdefault(farm.village_id, [])
    for animal in animals:
        farm = next(f for f in farms if f.id == animal.farm_id)
        by_village[farm.village_id].append(animal)

    presentations = [p for p, _ in BACKGROUND_PRESENTATIONS]
    weights = [w for _, w in BACKGROUND_PRESENTATIONS]

    for day in range(days):
        when = now - timedelta(days=days - day)
        # Roughly two or three reports a day across the district, more on
        # weekdays when field workers are out.
        daily = rng.choices([0, 1, 2, 3, 4], weights=[10, 24, 30, 22, 14])[0]
        for _ in range(daily):
            village = rng.choice(villages)
            candidates = by_village.get(village.id) or animals
            animal = rng.choice(candidates)
            farm = next(f for f in farms if f.id == animal.farm_id)
            symptoms = rng.choices(presentations, weights=weights, k=1)[0]

            reports.append(
                _make_report(
                    rng, animal, farm, village, symptoms, when, farm.owner_id, len(reports)
                )
            )

    # --------------------------------------------------------- injected event
    # A respiratory event in Sulibele over the last twelve days, accelerating.
    # This is what the demo walks through: several reports from nearby farms
    # that only mean something when they are looked at together.
    outbreak_village = next(v for v in villages if v.name == "Sulibele")
    outbreak_animals = [
        a for a in by_village.get(outbreak_village.id, [])
        if a.species in ("cattle", "buffalo")
    ]
    outbreak_profile = [
        (12, ["fever", "nasal_discharge"]),
        (10, ["fever", "cough"]),
        (8, ["fever", "cough", "nasal_discharge"]),
        (6, ["fever", "dyspnoea"]),
        (5, ["cough", "nasal_discharge"]),
        (4, ["fever", "cough"]),
        (3, ["fever", "cough", "lethargy"]),
        (2, ["fever", "dyspnoea", "lethargy"]),
        (1, ["fever", "cough"]),
    ]
    for offset, symptoms in outbreak_profile:
        if not outbreak_animals:
            break
        animal = rng.choice(outbreak_animals)
        farm = next(f for f in farms if f.id == animal.farm_id)
        report = _make_report(
            rng, animal, farm, outbreak_village, symptoms,
            now - timedelta(days=offset, hours=rng.randint(0, 20)),
            farm.owner_id, len(reports),
        )
        report.temperature_c = round(rng.uniform(39.8, 41.2), 1)
        report.affected_count = rng.randint(1, 3)
        reports.append(report)

    # A single severe standalone case, to exercise the caution floor.
    severe_village = next(v for v in villages if v.name == "Jadigenahalli")
    severe_candidates = by_village.get(severe_village.id) or animals
    severe_animal = rng.choice(severe_candidates)
    severe_farm = next(f for f in farms if f.id == severe_animal.farm_id)
    severe = _make_report(
        rng, severe_animal, severe_farm, severe_village,
        ["sudden_death", "bleeding_orifices"],
        now - timedelta(days=2), severe_farm.owner_id, len(reports),
    )
    severe.deaths_count = 1
    severe.affected_count = 1
    reports.append(severe)

    for report in reports:
        db.add(report)
    db.flush()

    for report in reports:
        assess_report(db, report)

    db.commit()

    return {
        **summary,
        "status": "seeded",
        "villages": len(villages),
        "farms": len(farms),
        "animals": len(animals),
        "reports": len(reports),
        "note": (
            "All livestock health data in this dataset is synthetic and is intended "
            "for demonstration and testing only."
        ),
    }


def _make_report(
    rng: random.Random,
    animal: Animal,
    farm: Farm,
    village: Village,
    symptoms: list[str],
    when: datetime,
    reporter_id: str,
    sequence: int,
) -> HealthReport:
    return HealthReport(
        client_uuid=f"seed-{sequence:05d}-{rng.randint(1000, 9999)}",
        animal_id=animal.id,
        farm_id=farm.id,
        village_id=village.id,
        reporter_id=reporter_id,
        species=animal.species,
        reported_at=when,
        received_at=when + timedelta(minutes=rng.randint(1, 240)),
        symptoms_text="",
        symptom_codes=list(symptoms),
        unmatched_terms=[],
        temperature_c=round(rng.uniform(38.2, 40.6), 1) if rng.random() < 0.45 else None,
        duration_hours=rng.choice([None, 6, 12, 24, 48, 72, 120]),
        affected_count=1,
        deaths_count=0,
        herd_size=max(1, len(farm.animals)) if farm.animals else None,
        latitude=_jitter(rng, farm.latitude, 0.004),
        longitude=_jitter(rng, farm.longitude, 0.004),
        notes="",
        submitted_offline=rng.random() < 0.35,
    )
