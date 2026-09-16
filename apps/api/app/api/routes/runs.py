"""Agent run inspection."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import or_, select
from sqlalchemy.orm import selectinload

from app.core.deps import DbSession, require_permission
from app.core.errors import NotFoundError
from app.core.pagination import Page, PageParams, apply_sort, page_params, paginate
from app.db.models import AgentRun, User
from app.schemas import RunDetail, RunSummary

router = APIRouter(prefix="/runs", tags=["agent runs"])


@router.get("", response_model=Page[RunSummary])
def list_runs(
    db: DbSession,
    params: PageParams = Depends(page_params),
    agent_id: uuid.UUID | None = None,
    status_filter: str | None = None,
    _: User = Depends(require_permission("agents:read")),
) -> Page[RunSummary]:
    stmt = select(AgentRun)
    if agent_id:
        stmt = stmt.where(AgentRun.agent_id == agent_id)
    if status_filter:
        stmt = stmt.where(AgentRun.status == status_filter)
    if params.q:
        needle = f"%{params.q.lower()}%"
        stmt = stmt.where(
            or_(AgentRun.input_text.ilike(needle), AgentRun.output_text.ilike(needle))
        )
    stmt = apply_sort(stmt, AgentRun, params, "created_at")
    rows, total = paginate(db, stmt, params)
    return Page.build([RunSummary.model_validate(row) for row in rows], total, params)


@router.get("/{run_id}", response_model=RunDetail)
def get_run(
    run_id: uuid.UUID,
    db: DbSession,
    _: User = Depends(require_permission("agents:read")),
) -> RunDetail:
    run = db.execute(
        select(AgentRun).options(selectinload(AgentRun.steps)).where(AgentRun.id == run_id)
    ).scalar_one_or_none()
    if run is None:
        raise NotFoundError("Run not found.")
    return RunDetail.model_validate(run)
