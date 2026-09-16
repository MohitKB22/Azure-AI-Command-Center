"""Token and cost center."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select

from app.core.deps import DbSession, require_permission
from app.core.pagination import Page, PageParams, apply_sort, page_params, paginate
from app.db.models import Agent, UsageRecord, User
from app.schemas import CostSummaryResponse
from app.services import costs

router = APIRouter(prefix="/costs", tags=["costs"])


@router.get("/summary", response_model=CostSummaryResponse)
def summary(
    db: DbSession,
    days: int = Query(30, ge=1, le=365),
    _: User = Depends(require_permission("costs:read")),
) -> CostSummaryResponse:
    since = datetime.now(timezone.utc) - timedelta(days=days)
    by_agent = costs.usage_by_dimension(db, UsageRecord.agent_id, days=days)

    # Replace agent UUIDs with names so the UI does not need a second lookup.
    agent_names = {
        str(agent_id): name
        for agent_id, name in db.execute(select(Agent.id, Agent.name)).all()
    }
    for row in by_agent:
        row["key"] = agent_names.get(row["key"], row["key"])

    return CostSummaryResponse(
        totals=costs.usage_totals(db, since=since),
        timeseries=costs.usage_timeseries(db, days=min(days, 60)),
        by_model=costs.usage_by_dimension(db, UsageRecord.model_name, days=days),
        by_agent=by_agent,
        by_team=costs.usage_by_dimension(db, UsageRecord.team, days=days),
        budgets=costs.budget_status(db),
    )


@router.get("/records")
def list_records(
    db: DbSession,
    params: PageParams = Depends(page_params),
    _: User = Depends(require_permission("costs:read")),
) -> Page[dict]:
    stmt = select(UsageRecord)
    if params.q:
        stmt = stmt.where(UsageRecord.model_name.ilike(f"%{params.q.lower()}%"))
    stmt = apply_sort(stmt, UsageRecord, params, "occurred_at")
    rows, total = paginate(db, stmt, params)
    items = [
        {
            "id": str(row.id),
            "run_id": str(row.run_id) if row.run_id else None,
            "model_name": row.model_name,
            "team": row.team,
            "operation": row.operation,
            "prompt_tokens": row.prompt_tokens,
            "completion_tokens": row.completion_tokens,
            "total_tokens": row.total_tokens,
            "estimated_cost": row.estimated_cost,
            "currency": row.currency,
            "latency_ms": row.latency_ms,
            "succeeded": row.succeeded,
            "occurred_at": row.occurred_at,
        }
        for row in rows
    ]
    return Page.build(items, total, params)
