"""Farms, animals, vaccinations, and treatment records."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..audit import record
from ..db import get_db
from ..models import Animal, Farm, Role, Treatment, User, Vaccination, Village, utcnow
from ..schemas import (
    AnimalCreate,
    AnimalOut,
    AnimalUpdate,
    FarmCreate,
    FarmOut,
    TreatmentCreate,
    TreatmentOut,
    VaccinationCreate,
    VaccinationOut,
    VillageOut,
)
from ..security import get_current_user, require_clinical, require_staff

router = APIRouter(tags=["livestock"])


def _owned_farm(db: Session, farm_id: str, user: User) -> Farm:
    farm = db.get(Farm, farm_id)
    if farm is None:
        raise HTTPException(status_code=404, detail="Farm not found.")
    if user.role is Role.FARMER and farm.owner_id != user.id:
        raise HTTPException(status_code=404, detail="Farm not found.")
    return farm


def _visible_animal(db: Session, animal_id: str, user: User) -> Animal:
    animal = db.get(Animal, animal_id)
    if animal is None:
        raise HTTPException(status_code=404, detail="Animal not found.")
    farm = db.get(Farm, animal.farm_id)
    if user.role is Role.FARMER and (farm is None or farm.owner_id != user.id):
        raise HTTPException(status_code=404, detail="Animal not found.")
    return animal


# ------------------------------------------------------------------ villages


@router.get("/villages", response_model=list[VillageOut])
def list_villages(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    block: str | None = Query(default=None),
    district: str | None = Query(default=None),
) -> list[Village]:
    stmt = select(Village)
    if block:
        stmt = stmt.where(Village.block == block)
    if district:
        stmt = stmt.where(Village.district == district)
    return list(db.scalars(stmt.order_by(Village.name)).all())


# --------------------------------------------------------------------- farms


@router.post("/farms", response_model=FarmOut, status_code=status.HTTP_201_CREATED)
def create_farm(
    payload: FarmCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Farm:
    if db.get(Village, payload.village_id) is None:
        raise HTTPException(status_code=404, detail="Village not found.")

    farm = Farm(
        name=payload.name,
        owner_id=user.id,
        village_id=payload.village_id,
        latitude=payload.latitude,
        longitude=payload.longitude,
    )
    db.add(farm)
    db.flush()
    record(db, user, "farm.create", entity_type="farm", entity_id=farm.id)
    db.commit()
    db.refresh(farm)
    return farm


@router.get("/farms", response_model=list[FarmOut])
def list_farms(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> list[Farm]:
    stmt = select(Farm)
    if user.role is Role.FARMER:
        stmt = stmt.where(Farm.owner_id == user.id)
    elif user.block:
        village_ids = db.scalars(
            select(Village.id).where(Village.block == user.block)
        ).all()
        stmt = stmt.where(Farm.village_id.in_(list(village_ids)))
    return list(db.scalars(stmt.order_by(Farm.name)).all())


# ------------------------------------------------------------------- animals


@router.post("/animals", response_model=AnimalOut, status_code=status.HTTP_201_CREATED)
def create_animal(
    payload: AnimalCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Animal:
    _owned_farm(db, payload.farm_id, user)

    clash = db.scalar(
        select(Animal).where(Animal.farm_id == payload.farm_id, Animal.tag == payload.tag)
    )
    if clash is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Tag '{payload.tag}' is already used in this farm.",
        )

    animal = Animal(**payload.model_dump())
    db.add(animal)
    db.flush()
    record(db, user, "animal.create", entity_type="animal", entity_id=animal.id)
    db.commit()
    db.refresh(animal)
    return animal


@router.get("/animals", response_model=list[AnimalOut])
def list_animals(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    farm_id: str | None = Query(default=None),
) -> list[Animal]:
    stmt = select(Animal)
    if farm_id:
        _owned_farm(db, farm_id, user)
        stmt = stmt.where(Animal.farm_id == farm_id)
    elif user.role is Role.FARMER:
        owned = db.scalars(select(Farm.id).where(Farm.owner_id == user.id)).all()
        stmt = stmt.where(Animal.farm_id.in_(list(owned)))
    return list(db.scalars(stmt.order_by(Animal.tag)).all())


@router.get("/animals/{animal_id}", response_model=AnimalOut)
def get_animal(
    animal_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> Animal:
    return _visible_animal(db, animal_id, user)


@router.patch("/animals/{animal_id}", response_model=AnimalOut)
def update_animal(
    animal_id: str,
    payload: AnimalUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Animal:
    animal = _visible_animal(db, animal_id, user)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(animal, field, value)
    record(db, user, "animal.update", entity_type="animal", entity_id=animal.id,
           detail=payload.model_dump(exclude_unset=True, mode="json"))
    db.commit()
    db.refresh(animal)
    return animal


@router.get("/animals/{animal_id}/timeline", response_model=dict)
def animal_timeline(
    animal_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> dict:
    """Everything on record for one animal, in one chronological list.

    This is the view a veterinarian opens before a field visit: what was
    reported, what was given, when it was vaccinated, and how the triage band
    moved over time.
    """
    animal = _visible_animal(db, animal_id, user)

    events: list[dict] = []
    for report in animal.reports:
        events.append({
            "type": "health_report",
            "at": report.reported_at.isoformat(),
            "id": report.id,
            "summary": ", ".join(report.symptom_codes or []) or report.symptoms_text[:120],
            "band": report.assessment.band if report.assessment else None,
            "score": report.assessment.score if report.assessment else None,
            "deaths": report.deaths_count,
        })
    for vaccination in animal.vaccinations:
        events.append({
            "type": "vaccination",
            "at": vaccination.administered_on.isoformat(),
            "id": vaccination.id,
            "summary": vaccination.vaccine,
            "next_due": vaccination.next_due_on.isoformat() if vaccination.next_due_on else None,
        })
    for treatment in animal.treatments:
        events.append({
            "type": "treatment",
            "at": treatment.administered_on.isoformat(),
            "id": treatment.id,
            "summary": treatment.description,
            "withdrawal_until": treatment.withdrawal_until.isoformat()
            if treatment.withdrawal_until else None,
        })

    events.sort(key=lambda e: e["at"], reverse=True)
    return {
        "animal": AnimalOut.model_validate(animal).model_dump(mode="json"),
        "events": events,
    }


# -------------------------------------------------------------- vaccinations


@router.post(
    "/vaccinations", response_model=VaccinationOut, status_code=status.HTTP_201_CREATED
)
def create_vaccination(
    payload: VaccinationCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_staff),
) -> Vaccination:
    _visible_animal(db, payload.animal_id, user)
    vaccination = Vaccination(**payload.model_dump(), administered_by=user.id)
    db.add(vaccination)
    db.flush()
    record(db, user, "vaccination.create", entity_type="vaccination", entity_id=vaccination.id)
    db.commit()
    db.refresh(vaccination)
    return vaccination


@router.get("/vaccinations/due", response_model=list[VaccinationOut])
def vaccinations_due(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    days: int = Query(default=30, ge=0, le=365),
) -> list[Vaccination]:
    """Boosters overdue now, or falling due within ``days``."""
    from datetime import timedelta

    horizon = utcnow() + timedelta(days=days)
    stmt = select(Vaccination).where(
        Vaccination.next_due_on.is_not(None), Vaccination.next_due_on <= horizon
    )
    if user.role is Role.FARMER:
        owned = db.scalars(select(Farm.id).where(Farm.owner_id == user.id)).all()
        animal_ids = db.scalars(
            select(Animal.id).where(Animal.farm_id.in_(list(owned)))
        ).all()
        stmt = stmt.where(Vaccination.animal_id.in_(list(animal_ids)))
    return list(db.scalars(stmt.order_by(Vaccination.next_due_on)).all())


# ---------------------------------------------------------------- treatments


@router.post("/treatments", response_model=TreatmentOut, status_code=status.HTTP_201_CREATED)
def create_treatment(
    payload: TreatmentCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_clinical),
) -> Treatment:
    """Record a treatment a veterinarian has given.

    Restricted to clinical roles. The platform documents treatment; it never
    proposes one, and a farmer cannot enter one on a vet's behalf.
    """
    if db.get(Animal, payload.animal_id) is None:
        raise HTTPException(status_code=404, detail="Animal not found.")

    treatment = Treatment(**payload.model_dump(), administered_by=user.id)
    db.add(treatment)
    db.flush()
    record(db, user, "treatment.create", entity_type="treatment", entity_id=treatment.id)
    db.commit()
    db.refresh(treatment)
    return treatment
