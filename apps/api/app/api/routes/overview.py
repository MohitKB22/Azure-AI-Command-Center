"""Overview dashboard aggregate."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select

from app.core.config import settings
from app.core.deps import DbSession, require_permission
from app.db.models import Agent, AgentRun, Alert, Document, UsageRecord, User
from app.providers.registry import provider_summary
from app.schemas import AlertOut, OverviewResponse, RunSummary
from app.services import costs
from app.services.monitoring import system_health

router = APIRouter(tags=["overview"])


@router.get("/overview", response_model=OverviewResponse)
def overview(
    db: DbSession,
    days: int = Query(14, ge=1, le=90),
    _: User = Depends(require_permission("monitoring:read")),
) -> OverviewResponse:
    since = datetime.now(timezone.utc) - timedelta(days=days)
    totals = costs.usage_totals(db, since=since)

    active_agents = db.scalar(
        select(func.count(Agent.id)).where(
            Agent.deleted_at.is_(None), Agent.enabled.is_(True)
        )
    ) or 0
    total_agents = db.scalar(
        select(func.count(Agent.id)).where(Agent.deleted_at.is_(None))
    ) or 0
    indexed_documents = db.scalar(
        select(func.count(Document.id)).where(
            Document.deleted_at.is_(None), Document.status == "indexed"
        )
    ) or 0

    runs_since = db.execute(
        select(AgentRun.status, AgentRun.citations, AgentRun.latency_ms).where(
            AgentRun.created_at >= since
        )
    ).all()
    total_runs = len(runs_since)
    grounded_runs = sum(1 for _, citations, _ in runs_since if citations)
    failed_runs = sum(1 for status, _, _ in runs_since if status in {"failed", "blocked"})

    recent_runs = list(
        db.execute(select(AgentRun).order_by(AgentRun.created_at.desc()).limit(8))
        .scalars()
        .all()
    )
    active_alerts = list(
        db.execute(
            select(Alert)
            .where(Alert.status == "active")
            .order_by(Alert.created_at.desc())
            .limit(6)
        )
        .scalars()
        .all()
    )

    agent_rows = db.execute(
        select(Agent.name, func.count(AgentRun.id))
        .join(AgentRun, AgentRun.agent_id == Agent.id)
        .where(AgentRun.created_at >= since)
        .group_by(Agent.name)
        .order_by(func.count(AgentRun.id).desc())
        .limit(8)
    ).all()

    return OverviewResponse(
        generated_at=datetime.now(timezone.utc),
        demo_mode=settings.demo_mode,
        environment=settings.environment,
        providers=provider_summary(),
        kpis={
            "active_agents": int(active_agents),
            "total_agents": int(total_agents),
            "indexed_documents": int(indexed_documents),
            "total_requests": totals["requests"],
            "total_tokens": totals["total_tokens"],
            "estimated_cost": totals["estimated_cost"],
            "avg_latency_ms": totals["avg_latency_ms"],
            "error_rate_pct": round((failed_runs / total_runs * 100) if total_runs else 0.0, 2),
            "agent_runs": total_runs,
            "rag_grounded_pct": round(
                (grounded_runs / total_runs * 100) if total_runs else 0.0, 2
            ),
            "active_alerts": len(active_alerts),
            "window_days": days,
        },
        timeseries=costs.usage_timeseries(db, days=days),
        model_usage=costs.usage_by_dimension(db, UsageRecord.model_name, days=days),
        agent_activity=[{"name": name, "runs": int(count)} for name, count in agent_rows],
        recent_runs=[RunSummary.model_validate(run) for run in recent_runs],
        active_alerts=[AlertOut.model_validate(alert) for alert in active_alerts],
        health=system_health(db),
    )
