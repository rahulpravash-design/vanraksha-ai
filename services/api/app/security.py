"""Authentication, password handling, and role-based access control.

The access-control model is deliberately two-dimensional, because one dimension
is not enough for this domain:

* **Role** decides what kind of action is permitted (a farmer files reports, a
  veterinarian closes cases, an administrator sees aggregates).
* **Scope** decides whose records are visible. A veterinarian in one block has
  no business reading another district's farmer contact details, and enforcing
  that at the query layer rather than in the UI is the only version that counts.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from .config import get_settings
from .db import get_db
from .models import Role, User

settings = get_settings()

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)

ALGORITHM = "HS256"

#: Roles that may see records beyond their own farm.
STAFF_ROLES = frozenset(
    {Role.FIELD_WORKER, Role.VETERINARIAN, Role.LAB,
     Role.BLOCK_ADMIN, Role.DISTRICT_ADMIN, Role.SUPER_ADMIN}
)
#: Roles that may act clinically on a case.
CLINICAL_ROLES = frozenset({Role.VETERINARIAN, Role.SUPER_ADMIN})
#: Roles that may read district-wide aggregates.
ADMIN_ROLES = frozenset({Role.BLOCK_ADMIN, Role.DISTRICT_ADMIN, Role.SUPER_ADMIN})


#: bcrypt's own hard limit. Beyond this it truncates, which would let two
#: different long passwords authenticate each other -- so it is rejected rather
#: than silently accepted.
MAX_PASSWORD_BYTES = 72


def hash_password(password: str) -> str:
    encoded = password.encode("utf-8")
    if len(encoded) > MAX_PASSWORD_BYTES:
        raise ValueError(
            f"password must be at most {MAX_PASSWORD_BYTES} bytes when UTF-8 encoded"
        )
    return bcrypt.hashpw(encoded, bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """Constant-time check that never raises on malformed input.

    A stored hash can be malformed after a bad migration, and a login attempt
    against one must fail closed rather than return a 500 that tells an
    attacker the account exists.
    """
    try:
        encoded = plain.encode("utf-8")
    except (AttributeError, UnicodeEncodeError):
        return False
    if len(encoded) > MAX_PASSWORD_BYTES:
        return False
    try:
        return bcrypt.checkpw(encoded, hashed.encode("utf-8"))
    except (ValueError, TypeError, AttributeError):
        return False


def create_access_token(subject: str, role: str, extra: dict[str, Any] | None = None) -> str:
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": subject,
        "role": role,
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_minutes),
        "typ": "access",
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def decode_token(token: str) -> dict[str, Any]:
    try:
        return jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired. Sign in again.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    except jwt.InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


def get_current_user(
    token: str | None = Depends(oauth2_scheme), db: Session = Depends(get_db)
) -> User:
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    payload = decode_token(token)
    if payload.get("typ") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Wrong token type.")

    user = db.get(User, payload.get("sub"))
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unknown user.")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is disabled.")
    return user


def require_roles(*roles: Role):
    """Dependency factory gating an endpoint on the caller's role."""
    allowed = frozenset(roles)

    def _guard(user: User = Depends(get_current_user)) -> User:
        if user.role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"This action requires one of: "
                    f"{', '.join(sorted(r.value for r in allowed))}."
                ),
            )
        return user

    return _guard


def require_staff(user: User = Depends(get_current_user)) -> User:
    if user.role not in STAFF_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This action is restricted to field and veterinary staff.",
        )
    return user


def require_clinical(user: User = Depends(get_current_user)) -> User:
    if user.role not in CLINICAL_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only veterinary staff may record clinical actions.",
        )
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role not in ADMIN_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This view is restricted to block and district administrators.",
        )
    return user


def visible_scope(user: User) -> dict[str, Any]:
    """The geographic slice of data this user may read.

    Returned as a filter description rather than applied directly so that each
    query can translate it into its own joins -- and so it can be unit-tested
    without a database.
    """
    if user.role in (Role.SUPER_ADMIN, Role.DISTRICT_ADMIN):
        return {"level": "district", "district": user.district}
    if user.role in (Role.BLOCK_ADMIN, Role.VETERINARIAN, Role.LAB):
        return {"level": "block", "block": user.block, "district": user.district}
    if user.role is Role.FIELD_WORKER:
        return {"level": "block", "block": user.block, "district": user.district}
    return {"level": "own", "user_id": user.id}


def can_read_report(user: User, report_owner_id: str, report_block: str | None) -> bool:
    """Whether ``user`` may read a report filed by ``report_owner_id``."""
    if user.role is Role.SUPER_ADMIN:
        return True
    if user.id == report_owner_id:
        return True
    if user.role is Role.FARMER:
        return False
    if user.role is Role.DISTRICT_ADMIN:
        return True
    return report_block is not None and report_block == user.block


def roles_for_audience(audience: str) -> Iterable[Role]:
    """Map an engine audience label onto the roles that should be notified."""
    return {
        "farmer": (Role.FARMER,),
        "field_worker": (Role.FIELD_WORKER,),
        "veterinarian": (Role.VETERINARIAN,),
        "block_admin": (Role.BLOCK_ADMIN,),
        "district_admin": (Role.DISTRICT_ADMIN, Role.SUPER_ADMIN),
    }.get(audience, ())
