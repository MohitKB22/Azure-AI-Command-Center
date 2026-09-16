"""Prompt registry with versioning, promotion, rendering and rollback."""

from __future__ import annotations

import re
import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy import or_, select
from sqlalchemy.orm import selectinload

from app.core.db import utcnow
from app.core.deps import DbSession, require_permission
from app.core.errors import ConflictError, NotFoundError, ValidationError
from app.core.pagination import Page, PageParams, apply_sort, page_params, paginate
from app.db.models import Prompt, PromptVersion, User
from app.schemas import (
    PromptCreate,
    PromptDetail,
    PromptOut,
    PromptRenderRequest,
    PromptRenderResponse,
    PromptVersionCreate,
    PromptVersionOut,
)
from app.services import audit

router = APIRouter(prefix="/prompts", tags=["prompts"])

_VARIABLE_RE = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}")


def extract_variables(template: str) -> list[str]:
    return sorted(set(_VARIABLE_RE.findall(template)))


def render_template(template: str, variables: dict[str, str]) -> tuple[str, list[str]]:
    missing: list[str] = []

    def _replace(match: re.Match[str]) -> str:
        name = match.group(1)
        if name not in variables:
            missing.append(name)
            return match.group(0)
        return str(variables[name])

    return _VARIABLE_RE.sub(_replace, template), sorted(set(missing))


def _load(db, prompt_id: uuid.UUID) -> Prompt:
    prompt = db.execute(
        select(Prompt).options(selectinload(Prompt.versions)).where(Prompt.id == prompt_id)
    ).scalar_one_or_none()
    if prompt is None or prompt.deleted_at is not None:
        raise NotFoundError("Prompt not found.")
    return prompt


@router.get("", response_model=Page[PromptOut])
def list_prompts(
    db: DbSession,
    params: PageParams = Depends(page_params),
    _: User = Depends(require_permission("prompts:read")),
) -> Page[PromptOut]:
    stmt = select(Prompt).where(Prompt.deleted_at.is_(None))
    if params.q:
        needle = f"%{params.q.lower()}%"
        stmt = stmt.where(or_(Prompt.name.ilike(needle), Prompt.key.ilike(needle)))
    stmt = apply_sort(stmt, Prompt, params, "updated_at")
    rows, total = paginate(db, stmt, params)
    return Page.build([PromptOut.model_validate(row) for row in rows], total, params)


@router.post("", response_model=PromptDetail, status_code=status.HTTP_201_CREATED)
def create_prompt(
    payload: PromptCreate,
    db: DbSession,
    user: User = Depends(require_permission("prompts:write")),
) -> PromptDetail:
    if db.execute(select(Prompt).where(Prompt.key == payload.key)).scalar_one_or_none():
        raise ConflictError("A prompt with that key already exists.")

    prompt = Prompt(
        key=payload.key,
        name=payload.name,
        description=payload.description,
        tags=payload.tags,
        owner_id=user.id,
        active_version=1,
    )
    db.add(prompt)
    db.flush()
    db.add(
        PromptVersion(
            prompt_id=prompt.id,
            version=1,
            template=payload.template,
            variables=extract_variables(payload.template),
            changelog="Initial version",
            created_by=user.id,
        )
    )
    audit.record(
        db,
        action="prompt.create",
        resource_type="prompt",
        resource_id=prompt.id,
        actor=user,
        changes={"key": prompt.key},
    )
    db.commit()
    return PromptDetail.model_validate(_load(db, prompt.id))


@router.get("/{prompt_id}", response_model=PromptDetail)
def get_prompt(
    prompt_id: uuid.UUID,
    db: DbSession,
    _: User = Depends(require_permission("prompts:read")),
) -> PromptDetail:
    return PromptDetail.model_validate(_load(db, prompt_id))


@router.post("/{prompt_id}/versions", response_model=PromptVersionOut,
             status_code=status.HTTP_201_CREATED)
def create_version(
    prompt_id: uuid.UUID,
    payload: PromptVersionCreate,
    db: DbSession,
    user: User = Depends(require_permission("prompts:write")),
) -> PromptVersion:
    prompt = _load(db, prompt_id)
    next_version = max((v.version for v in prompt.versions), default=0) + 1
    version = PromptVersion(
        prompt_id=prompt.id,
        version=next_version,
        template=payload.template,
        variables=extract_variables(payload.template),
        environment=payload.environment,
        approval_status=payload.approval_status,
        changelog=payload.changelog,
        created_by=user.id,
    )
    db.add(version)
    prompt.active_version = next_version
    audit.record(
        db,
        action="prompt.version",
        resource_type="prompt",
        resource_id=prompt.id,
        actor=user,
        changes={"version": next_version, "environment": payload.environment},
    )
    db.commit()
    db.refresh(version)
    return version


@router.post("/{prompt_id}/rollback/{version}", response_model=PromptDetail)
def rollback(
    prompt_id: uuid.UUID,
    version: int,
    db: DbSession,
    user: User = Depends(require_permission("prompts:write")),
) -> PromptDetail:
    prompt = _load(db, prompt_id)
    if not any(v.version == version for v in prompt.versions):
        raise NotFoundError(f"Version {version} does not exist.")
    prompt.active_version = version
    audit.record(
        db,
        action="prompt.rollback",
        resource_type="prompt",
        resource_id=prompt.id,
        actor=user,
        changes={"active_version": version},
    )
    db.commit()
    return PromptDetail.model_validate(_load(db, prompt_id))


@router.post("/{prompt_id}/render", response_model=PromptRenderResponse)
def render(
    prompt_id: uuid.UUID,
    payload: PromptRenderRequest,
    db: DbSession,
    _: User = Depends(require_permission("prompts:execute")),
) -> PromptRenderResponse:
    prompt = _load(db, prompt_id)
    target = payload.version or prompt.active_version
    version = next((v for v in prompt.versions if v.version == target), None)
    if version is None:
        raise NotFoundError(f"Version {target} does not exist.")
    rendered, missing = render_template(version.template, payload.variables)
    return PromptRenderResponse(rendered=rendered, missing_variables=missing, version=target)


@router.delete("/{prompt_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_prompt(
    prompt_id: uuid.UUID,
    db: DbSession,
    user: User = Depends(require_permission("prompts:delete")),
) -> None:
    prompt = _load(db, prompt_id)
    prompt.deleted_at = utcnow()
    audit.record(
        db, action="prompt.delete", resource_type="prompt", resource_id=prompt.id, actor=user
    )
    db.commit()


@router.post("/{prompt_id}/promote/{version}", response_model=PromptVersionOut)
def promote(
    prompt_id: uuid.UUID,
    version: int,
    environment: str,
    db: DbSession,
    user: User = Depends(require_permission("prompts:write")),
) -> PromptVersion:
    if environment not in {"development", "staging", "production"}:
        raise ValidationError("environment must be development, staging or production.")
    prompt = _load(db, prompt_id)
    target = next((v for v in prompt.versions if v.version == version), None)
    if target is None:
        raise NotFoundError(f"Version {version} does not exist.")
    if environment == "production" and target.approval_status != "approved":
        raise ValidationError("Only approved versions can be promoted to production.")
    target.environment = environment
    audit.record(
        db,
        action="prompt.promote",
        resource_type="prompt",
        resource_id=prompt.id,
        actor=user,
        changes={"version": version, "environment": environment},
    )
    db.commit()
    db.refresh(target)
    return target
