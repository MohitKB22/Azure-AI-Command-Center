"""Agent CRUD, versioning and execution."""

from __future__ import annotations

import re
import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy import or_, select

from app.core.db import utcnow
from app.core.deps import DbSession, require_permission
from app.core.errors import ConflictError, NotFoundError, ValidationError
from app.core.pagination import Page, PageParams, apply_sort, page_params, paginate
from app.db.models import Agent, AgentVersion, ModelCatalogEntry, User
from app.schemas import (
    AgentCreate,
    AgentDetail,
    AgentRunRequest,
    AgentSummary,
    AgentUpdate,
    AgentVersionOut,
    RunDetail,
)
from app.services import audit
from app.services.agent_graph import GRAPH_TOPOLOGY
from app.services.runner import execute_agent
from app.services.tools import tool_catalog

router = APIRouter(prefix="/agents", tags=["agents"])

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slugify(name: str) -> str:
    slug = _SLUG_RE.sub("-", name.lower()).strip("-")
    return slug or "agent"


def _unique_slug(db, name: str) -> str:
    base = _slugify(name)
    slug = base
    suffix = 2
    while db.execute(select(Agent.id).where(Agent.slug == slug)).scalar_one_or_none():
        slug = f"{base}-{suffix}"
        suffix += 1
    return slug


def _snapshot(agent: Agent) -> dict:
    return {
        "name": agent.name,
        "description": agent.description,
        "system_prompt": agent.system_prompt,
        "model_id": str(agent.model_id) if agent.model_id else None,
        "fallback_model_id": str(agent.fallback_model_id) if agent.fallback_model_id else None,
        "temperature": agent.temperature,
        "max_output_tokens": agent.max_output_tokens,
        "timeout_seconds": agent.timeout_seconds,
        "max_retries": agent.max_retries,
        "tools": list(agent.tools or []),
        "memory_enabled": agent.memory_enabled,
        "rag_enabled": agent.rag_enabled,
        "rag_pipeline_id": str(agent.rag_pipeline_id) if agent.rag_pipeline_id else None,
        "guardrail_policy_id": (
            str(agent.guardrail_policy_id) if agent.guardrail_policy_id else None
        ),
        "environment": agent.environment,
        "status": agent.status,
        "tags": list(agent.tags or []),
    }


def _load(db, agent_id: uuid.UUID) -> Agent:
    agent = db.get(Agent, agent_id)
    if agent is None or agent.deleted_at is not None:
        raise NotFoundError("Agent not found.")
    return agent


def _validate_models(db, model_id, fallback_model_id) -> None:
    for value, label in ((model_id, "model_id"), (fallback_model_id, "fallback_model_id")):
        if value is None:
            continue
        model = db.get(ModelCatalogEntry, value)
        if model is None or model.deleted_at is not None:
            raise ValidationError(f"{label} does not reference a known model.")
        if model.kind != "chat":
            raise ValidationError(f"{label} must reference a chat model.")


@router.get("", response_model=Page[AgentSummary])
def list_agents(
    db: DbSession,
    params: PageParams = Depends(page_params),
    status_filter: str | None = None,
    environment: str | None = None,
    enabled: bool | None = None,
    _: User = Depends(require_permission("agents:read")),
) -> Page[AgentSummary]:
    stmt = select(Agent).where(Agent.deleted_at.is_(None))
    if status_filter:
        stmt = stmt.where(Agent.status == status_filter)
    if environment:
        stmt = stmt.where(Agent.environment == environment)
    if enabled is not None:
        stmt = stmt.where(Agent.enabled.is_(enabled))
    if params.q:
        needle = f"%{params.q.lower()}%"
        stmt = stmt.where(or_(Agent.name.ilike(needle), Agent.description.ilike(needle)))
    stmt = apply_sort(stmt, Agent, params, "updated_at")
    rows, total = paginate(db, stmt, params)
    return Page.build([AgentSummary.model_validate(row) for row in rows], total, params)


@router.get("/graph-topology")
def graph_topology(_: User = Depends(require_permission("agents:read"))) -> dict:
    return {"nodes": GRAPH_TOPOLOGY, "tools": tool_catalog()}


@router.post("", response_model=AgentDetail, status_code=status.HTTP_201_CREATED)
def create_agent(
    payload: AgentCreate,
    db: DbSession,
    actor: User = Depends(require_permission("agents:write")),
) -> Agent:
    _validate_models(db, payload.model_id, payload.fallback_model_id)
    agent = Agent(
        **payload.model_dump(),
        slug=_unique_slug(db, payload.name),
        created_by=actor.id,
        updated_by=actor.id,
    )
    db.add(agent)
    db.flush()
    db.add(
        AgentVersion(
            agent_id=agent.id,
            version=1,
            snapshot=_snapshot(agent),
            changelog="Initial version",
            created_by=actor.id,
        )
    )
    audit.record(
        db,
        action="agent.create",
        resource_type="agent",
        resource_id=agent.id,
        actor=actor,
        changes={"name": agent.name},
    )
    db.commit()
    db.refresh(agent)
    return agent


@router.get("/{agent_id}", response_model=AgentDetail)
def get_agent(
    agent_id: uuid.UUID,
    db: DbSession,
    _: User = Depends(require_permission("agents:read")),
) -> Agent:
    return _load(db, agent_id)


@router.patch("/{agent_id}", response_model=AgentDetail)
def update_agent(
    agent_id: uuid.UUID,
    payload: AgentUpdate,
    db: DbSession,
    actor: User = Depends(require_permission("agents:write")),
) -> Agent:
    agent = _load(db, agent_id)
    before = _snapshot(agent)
    data = payload.model_dump(exclude_unset=True)
    _validate_models(
        db,
        data.get("model_id", agent.model_id),
        data.get("fallback_model_id", agent.fallback_model_id),
    )
    for field, value in data.items():
        setattr(agent, field, value)
    if "name" in data and data["name"]:
        agent.slug = agent.slug  # slug is stable across renames by design
    agent.updated_by = actor.id
    db.flush()

    after = _snapshot(agent)
    if after != before:
        agent.current_version += 1
        db.add(
            AgentVersion(
                agent_id=agent.id,
                version=agent.current_version,
                snapshot=after,
                changelog="Configuration updated",
                created_by=actor.id,
            )
        )
    audit.record(
        db,
        action="agent.update",
        resource_type="agent",
        resource_id=agent.id,
        actor=actor,
        changes=audit.diff(before, after),
    )
    db.commit()
    db.refresh(agent)
    return agent


@router.delete("/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_agent(
    agent_id: uuid.UUID,
    db: DbSession,
    actor: User = Depends(require_permission("agents:delete")),
) -> None:
    agent = _load(db, agent_id)
    agent.deleted_at = utcnow()
    agent.enabled = False
    agent.status = "archived"
    audit.record(
        db, action="agent.delete", resource_type="agent", resource_id=agent.id, actor=actor
    )
    db.commit()


@router.post("/{agent_id}/duplicate", response_model=AgentDetail,
             status_code=status.HTTP_201_CREATED)
def duplicate_agent(
    agent_id: uuid.UUID,
    db: DbSession,
    actor: User = Depends(require_permission("agents:write")),
) -> Agent:
    source = _load(db, agent_id)
    name = f"{source.name} (copy)"
    clone = Agent(
        name=name,
        slug=_unique_slug(db, name),
        description=source.description,
        status="draft",
        environment=source.environment,
        enabled=False,
        system_prompt=source.system_prompt,
        model_id=source.model_id,
        fallback_model_id=source.fallback_model_id,
        temperature=source.temperature,
        max_output_tokens=source.max_output_tokens,
        timeout_seconds=source.timeout_seconds,
        max_retries=source.max_retries,
        tools=list(source.tools or []),
        memory_enabled=source.memory_enabled,
        rag_enabled=source.rag_enabled,
        rag_pipeline_id=source.rag_pipeline_id,
        guardrail_policy_id=source.guardrail_policy_id,
        tags=list(source.tags or []),
        created_by=actor.id,
        updated_by=actor.id,
    )
    db.add(clone)
    db.flush()
    db.add(
        AgentVersion(
            agent_id=clone.id,
            version=1,
            snapshot=_snapshot(clone),
            changelog=f"Duplicated from {source.slug}",
            created_by=actor.id,
        )
    )
    audit.record(
        db,
        action="agent.duplicate",
        resource_type="agent",
        resource_id=clone.id,
        actor=actor,
        changes={"source": str(source.id)},
    )
    db.commit()
    db.refresh(clone)
    return clone


@router.post("/{agent_id}/toggle", response_model=AgentDetail)
def toggle_agent(
    agent_id: uuid.UUID,
    db: DbSession,
    actor: User = Depends(require_permission("agents:write")),
) -> Agent:
    agent = _load(db, agent_id)
    agent.enabled = not agent.enabled
    agent.status = "active" if agent.enabled else "paused"
    audit.record(
        db,
        action="agent.toggle",
        resource_type="agent",
        resource_id=agent.id,
        actor=actor,
        changes={"enabled": agent.enabled},
    )
    db.commit()
    db.refresh(agent)
    return agent


@router.get("/{agent_id}/versions", response_model=list[AgentVersionOut])
def list_versions(
    agent_id: uuid.UUID,
    db: DbSession,
    _: User = Depends(require_permission("agents:read")),
) -> list[AgentVersion]:
    _load(db, agent_id)
    return list(
        db.execute(
            select(AgentVersion)
            .where(AgentVersion.agent_id == agent_id)
            .order_by(AgentVersion.version.desc())
        )
        .scalars()
        .all()
    )


@router.post("/{agent_id}/versions/{version}/rollback", response_model=AgentDetail)
def rollback_version(
    agent_id: uuid.UUID,
    version: int,
    db: DbSession,
    actor: User = Depends(require_permission("agents:write")),
) -> Agent:
    agent = _load(db, agent_id)
    target = db.execute(
        select(AgentVersion).where(
            AgentVersion.agent_id == agent_id, AgentVersion.version == version
        )
    ).scalar_one_or_none()
    if target is None:
        raise NotFoundError(f"Version {version} not found for this agent.")
    if version == agent.current_version:
        raise ConflictError("That version is already active.")

    snapshot = dict(target.snapshot or {})
    for field in ("model_id", "fallback_model_id", "rag_pipeline_id", "guardrail_policy_id"):
        value = snapshot.get(field)
        snapshot[field] = uuid.UUID(value) if value else None
    for field, value in snapshot.items():
        if hasattr(agent, field):
            setattr(agent, field, value)

    agent.current_version += 1
    agent.updated_by = actor.id
    db.add(
        AgentVersion(
            agent_id=agent.id,
            version=agent.current_version,
            snapshot=_snapshot(agent),
            changelog=f"Rolled back to version {version}",
            created_by=actor.id,
        )
    )
    audit.record(
        db,
        action="agent.rollback",
        resource_type="agent",
        resource_id=agent.id,
        actor=actor,
        changes={"to_version": version},
    )
    db.commit()
    db.refresh(agent)
    return agent


@router.post("/{agent_id}/run", response_model=RunDetail)
def run_agent(
    agent_id: uuid.UUID,
    payload: AgentRunRequest,
    db: DbSession,
    user: User = Depends(require_permission("agents:execute")),
) -> RunDetail:
    agent = _load(db, agent_id)
    run = execute_agent(
        db, agent, payload.input, user=user, correlation_id=payload.correlation_id
    )
    audit.record(
        db,
        action="agent.run",
        resource_type="agent_run",
        resource_id=run.id,
        actor=user,
        outcome="success" if run.status == "succeeded" else run.status,
        changes={"agent": agent.slug, "status": run.status},
    )
    db.commit()
    db.refresh(run)
    return RunDetail.model_validate(run)
