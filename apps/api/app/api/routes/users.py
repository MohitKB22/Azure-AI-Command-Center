"""User administration. Every route requires an explicit users:* permission."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy import or_, select

from app.core.deps import DbSession, require_permission
from app.core.errors import ConflictError, NotFoundError, ValidationError
from app.core.pagination import Page, PageParams, apply_sort, page_params, paginate
from app.core.rbac import ROLE_LABELS, Role, permissions_for
from app.core.security import hash_password
from app.db.models import User
from app.schemas import UserCreate, UserOut, UserUpdate
from app.services import audit

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=Page[UserOut])
def list_users(
    db: DbSession,
    params: PageParams = Depends(page_params),
    role: Role | None = None,
    _: User = Depends(require_permission("users:read")),
) -> Page[UserOut]:
    stmt = select(User).where(User.deleted_at.is_(None))
    if role:
        stmt = stmt.where(User.role == role.value)
    if params.q:
        needle = f"%{params.q.lower()}%"
        stmt = stmt.where(
            or_(User.email.ilike(needle), User.full_name.ilike(needle))
        )
    stmt = apply_sort(stmt, User, params, "created_at")
    rows, total = paginate(db, stmt, params)
    return Page.build([UserOut.model_validate(row) for row in rows], total, params)


@router.get("/roles")
def list_roles(_: User = Depends(require_permission("users:read"))) -> list[dict]:
    return [
        {
            "value": role.value,
            "label": ROLE_LABELS[role],
            "permissions": sorted(permissions_for(role)),
        }
        for role in Role
    ]


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_user(
    payload: UserCreate,
    db: DbSession,
    actor: User = Depends(require_permission("users:write")),
) -> User:
    email = payload.email.lower()
    if db.execute(select(User).where(User.email == email)).scalar_one_or_none():
        raise ConflictError("A user with that email already exists.")
    try:
        hashed = hash_password(payload.password)
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc

    user = User(
        email=email,
        full_name=payload.full_name,
        hashed_password=hashed,
        role=payload.role.value,
        team=payload.team,
    )
    db.add(user)
    audit.record(
        db,
        action="user.create",
        resource_type="user",
        resource_id=user.id,
        actor=actor,
        changes={"email": email, "role": payload.role.value},
    )
    db.commit()
    db.refresh(user)
    return user


@router.get("/{user_id}", response_model=UserOut)
def get_user(
    user_id: uuid.UUID,
    db: DbSession,
    _: User = Depends(require_permission("users:read")),
) -> User:
    user = db.get(User, user_id)
    if user is None or user.deleted_at is not None:
        raise NotFoundError("User not found.")
    return user


@router.patch("/{user_id}", response_model=UserOut)
def update_user(
    user_id: uuid.UUID,
    payload: UserUpdate,
    db: DbSession,
    actor: User = Depends(require_permission("users:write")),
) -> User:
    user = db.get(User, user_id)
    if user is None or user.deleted_at is not None:
        raise NotFoundError("User not found.")

    before = {"role": user.role, "team": user.team, "is_active": user.is_active}
    data = payload.model_dump(exclude_unset=True)
    if "role" in data and data["role"] is not None:
        data["role"] = Role(data["role"]).value
        if user.id == actor.id and data["role"] != Role.ADMIN.value:
            raise ValidationError("You cannot remove your own admin role.")
    for field, value in data.items():
        setattr(user, field, value)

    audit.record(
        db,
        action="user.update",
        resource_type="user",
        resource_id=user.id,
        actor=actor,
        changes=audit.diff(before, {"role": user.role, "team": user.team,
                                    "is_active": user.is_active}),
    )
    db.commit()
    db.refresh(user)
    return user


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def deactivate_user(
    user_id: uuid.UUID,
    db: DbSession,
    actor: User = Depends(require_permission("users:delete")),
) -> None:
    user = db.get(User, user_id)
    if user is None or user.deleted_at is not None:
        raise NotFoundError("User not found.")
    if user.id == actor.id:
        raise ValidationError("You cannot deactivate your own account.")
    from app.core.db import utcnow

    user.deleted_at = utcnow()
    user.is_active = False
    audit.record(
        db, action="user.delete", resource_type="user", resource_id=user.id, actor=actor
    )
    db.commit()
