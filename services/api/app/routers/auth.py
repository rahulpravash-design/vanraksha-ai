"""Registration and sign-in."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..audit import record
from ..config import get_settings
from ..db import get_db
from ..models import Role, User
from ..schemas import Token, UserCreate, UserOut
from ..security import create_access_token, get_current_user, hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])
settings = get_settings()

#: Roles a self-service registration may claim. Staff accounts are provisioned
#: by an administrator -- otherwise anyone could sign up as a district officer
#: and read every farmer's records.
SELF_SERVICE_ROLES = {Role.FARMER}


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register(payload: UserCreate, db: Session = Depends(get_db)) -> User:
    if payload.role not in SELF_SERVICE_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Only farmer accounts can be created by self-registration. "
                "Field, veterinary and administrative accounts are provisioned by an administrator."
            ),
        )

    existing = db.scalar(select(User).where(User.email == payload.email.lower()))
    if existing is not None:
        # Deliberately the same shape of error as any other failed registration:
        # a distinct message here would confirm which email addresses exist.
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="That email address cannot be registered.",
        )

    user = User(
        email=payload.email.lower(),
        hashed_password=hash_password(payload.password),
        full_name=payload.full_name,
        role=payload.role,
        phone=payload.phone,
        language=payload.language,
        village_id=payload.village_id,
        block=payload.block,
        district=payload.district,
    )
    db.add(user)
    db.flush()
    record(db, user, "user.register", entity_type="user", entity_id=user.id)
    db.commit()
    db.refresh(user)
    return user


@router.post("/login", response_model=Token)
def login(
    form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)
) -> Token:
    user = db.scalar(select(User).where(User.email == form.username.lower()))

    # Verify against a dummy hash when the user is missing so that response
    # timing does not reveal which addresses are registered.
    hashed = user.hashed_password if user else "$2b$12$" + "x" * 53
    password_ok = verify_password(form.password, hashed)

    if user is None or not password_ok:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Account is disabled."
        )

    record(db, user, "user.login", entity_type="user", entity_id=user.id)
    db.commit()

    return Token(
        access_token=create_access_token(user.id, user.role.value),
        expires_in=settings.access_token_minutes * 60,
        role=user.role,
        user_id=user.id,
        full_name=user.full_name,
    )


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)) -> User:
    return user
