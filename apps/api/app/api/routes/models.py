"""Model Center: catalog, routing defaults and cost configuration."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy import select

from app.core.db import utcnow
from app.core.deps import DbSession, require_permission
from app.core.errors import ConflictError, NotFoundError, ValidationError
from app.core.pagination import Page, PageParams, apply_sort, page_params, paginate
from app.db.models import Agent, ModelCatalogEntry, User
from app.schemas import ModelCreate, ModelOut, ModelUpdate
from app.services import audit

router = APIRouter(prefix="/models", tags=["models"])


def _clear_flag(db, field: str) -> None:
    column = getattr(ModelCatalogEntry, field)
    for entry in db.execute(
        select(ModelCatalogEntry).where(column.is_(True))
    ).scalars():
        setattr(entry, field, False)


@router.get("", response_model=Page[ModelOut])
def list_models(
    db: DbSession,
    params: PageParams = Depends(page_params),
    kind: str | None = None,
    _: User = Depends(require_permission("models:read")),
) -> Page[ModelOut]:
    stmt = select(ModelCatalogEntry).where(ModelCatalogEntry.deleted_at.is_(None))
    if kind:
        stmt = stmt.where(ModelCatalogEntry.kind == kind)
    if params.q:
        needle = f"%{params.q.lower()}%"
        stmt = stmt.where(ModelCatalogEntry.name.ilike(needle))
    stmt = apply_sort(stmt, ModelCatalogEntry, params, "name")
    rows, total = paginate(db, stmt, params)
    return Page.build([ModelOut.model_validate(row) for row in rows], total, params)


@router.post("", response_model=ModelOut, status_code=status.HTTP_201_CREATED)
def create_model(
    payload: ModelCreate,
    db: DbSession,
    user: User = Depends(require_permission("models:write")),
) -> ModelCatalogEntry:
    duplicate = db.execute(
        select(ModelCatalogEntry).where(
            ModelCatalogEntry.provider == payload.provider,
            ModelCatalogEntry.deployment_name == payload.deployment_name,
        )
    ).scalar_one_or_none()
    if duplicate:
        raise ConflictError("That provider/deployment combination already exists.")

    if payload.is_default:
        _clear_flag(db, "is_default")
    if payload.is_fallback:
        _clear_flag(db, "is_fallback")

    entry = ModelCatalogEntry(**payload.model_dump())
    db.add(entry)
    audit.record(
        db,
        action="model.create",
        resource_type="model",
        resource_id=entry.id,
        actor=user,
        changes={"name": entry.name, "deployment": entry.deployment_name},
    )
    db.commit()
    db.refresh(entry)
    return entry


@router.get("/{model_id}", response_model=ModelOut)
def get_model(
    model_id: uuid.UUID,
    db: DbSession,
    _: User = Depends(require_permission("models:read")),
) -> ModelCatalogEntry:
    entry = db.get(ModelCatalogEntry, model_id)
    if entry is None or entry.deleted_at is not None:
        raise NotFoundError("Model not found.")
    return entry


@router.patch("/{model_id}", response_model=ModelOut)
def update_model(
    model_id: uuid.UUID,
    payload: ModelUpdate,
    db: DbSession,
    user: User = Depends(require_permission("models:write")),
) -> ModelCatalogEntry:
    entry = db.get(ModelCatalogEntry, model_id)
    if entry is None or entry.deleted_at is not None:
        raise NotFoundError("Model not found.")

    data = payload.model_dump(exclude_unset=True)
    before = {
        "input_cost_per_1k": entry.input_cost_per_1k,
        "output_cost_per_1k": entry.output_cost_per_1k,
        "status": entry.status,
        "is_default": entry.is_default,
    }
    if data.get("is_default"):
        _clear_flag(db, "is_default")
    if data.get("is_fallback"):
        _clear_flag(db, "is_fallback")
    for field, value in data.items():
        setattr(entry, field, value)

    audit.record(
        db,
        action="model.update",
        resource_type="model",
        resource_id=entry.id,
        actor=user,
        changes=audit.diff(
            before,
            {
                "input_cost_per_1k": entry.input_cost_per_1k,
                "output_cost_per_1k": entry.output_cost_per_1k,
                "status": entry.status,
                "is_default": entry.is_default,
            },
        ),
    )
    db.commit()
    db.refresh(entry)
    return entry


@router.delete("/{model_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_model(
    model_id: uuid.UUID,
    db: DbSession,
    user: User = Depends(require_permission("models:delete")),
) -> None:
    entry = db.get(ModelCatalogEntry, model_id)
    if entry is None or entry.deleted_at is not None:
        raise NotFoundError("Model not found.")

    in_use = db.execute(
        select(Agent.id).where(
            Agent.deleted_at.is_(None),
            (Agent.model_id == model_id) | (Agent.fallback_model_id == model_id),
        ).limit(1)
    ).scalar_one_or_none()
    if in_use:
        raise ValidationError(
            "This model is assigned to at least one agent. Reassign those agents first."
        )

    entry.deleted_at = utcnow()
    entry.status = "retired"
    audit.record(
        db, action="model.delete", resource_type="model", resource_id=entry.id, actor=user
    )
    db.commit()
