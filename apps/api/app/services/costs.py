"""Cost calculation and usage recording.

Pricing is never hard-coded: it is read from the `models` table, so adding a
model or repricing one is a configuration change, not a code change.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Budget, ModelCatalogEntry, UsageRecord


@dataclass(slots=True)
class CostBreakdown:
    input_cost: float
    output_cost: float
    total_cost: float
    currency: str

    def rounded(self, places: int = 6) -> CostBreakdown:
        return CostBreakdown(
            input_cost=round(self.input_cost, places),
            output_cost=round(self.output_cost, places),
            total_cost=round(self.total_cost, places),
            currency=self.currency,
        )


def calculate_cost(
    model: ModelCatalogEntry | None,
    prompt_tokens: int,
    completion_tokens: int,
) -> CostBreakdown:
    """Cost = (tokens / 1000) * configured per-1k rate. Unknown model -> zero."""
    if model is None:
        return CostBreakdown(0.0, 0.0, 0.0, "USD")
    prompt_tokens = max(0, prompt_tokens)
    completion_tokens = max(0, completion_tokens)
    input_cost = (prompt_tokens / 1000.0) * (model.input_cost_per_1k or 0.0)
    output_cost = (completion_tokens / 1000.0) * (model.output_cost_per_1k or 0.0)
    return CostBreakdown(
        input_cost=input_cost,
        output_cost=output_cost,
        total_cost=input_cost + output_cost,
        currency=model.currency or "USD",
    ).rounded()


def record_usage(
    db: Session,
    *,
    model: ModelCatalogEntry | None,
    model_name: str,
    prompt_tokens: int,
    completion_tokens: int,
    latency_ms: int,
    run_id: uuid.UUID | None = None,
    agent_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
    team: str | None = None,
    operation: str = "chat",
    succeeded: bool = True,
    is_demo: bool = False,
    occurred_at: datetime | None = None,
) -> UsageRecord:
    cost = calculate_cost(model, prompt_tokens, completion_tokens)
    record = UsageRecord(
        run_id=run_id,
        agent_id=agent_id,
        user_id=user_id,
        model_id=model.id if model else None,
        model_name=model_name,
        team=team,
        operation=operation,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=prompt_tokens + completion_tokens,
        estimated_cost=cost.total_cost,
        currency=cost.currency,
        latency_ms=latency_ms,
        succeeded=succeeded,
        is_demo=is_demo,
        occurred_at=occurred_at or datetime.now(timezone.utc),
    )
    db.add(record)
    db.flush()
    return record


def usage_totals(db: Session, *, since: datetime | None = None) -> dict:
    stmt = select(
        func.count(UsageRecord.id),
        func.coalesce(func.sum(UsageRecord.prompt_tokens), 0),
        func.coalesce(func.sum(UsageRecord.completion_tokens), 0),
        func.coalesce(func.sum(UsageRecord.total_tokens), 0),
        func.coalesce(func.sum(UsageRecord.estimated_cost), 0.0),
        func.coalesce(func.avg(UsageRecord.latency_ms), 0.0),
    )
    if since:
        stmt = stmt.where(UsageRecord.occurred_at >= since)
    requests, prompt, completion, total, cost, latency = db.execute(stmt).one()

    failures = db.scalar(
        select(func.count(UsageRecord.id)).where(
            UsageRecord.succeeded.is_(False),
            *( [UsageRecord.occurred_at >= since] if since else [] ),
        )
    ) or 0

    return {
        "requests": int(requests or 0),
        "prompt_tokens": int(prompt or 0),
        "completion_tokens": int(completion or 0),
        "total_tokens": int(total or 0),
        "estimated_cost": round(float(cost or 0.0), 4),
        "avg_latency_ms": int(latency or 0),
        "error_rate_pct": round((failures / requests * 100) if requests else 0.0, 2),
    }


def usage_timeseries(db: Session, *, days: int = 14) -> list[dict]:
    """Daily aggregation. Grouped in Python so SQLite and PostgreSQL agree."""
    since = datetime.now(timezone.utc) - timedelta(days=days)
    rows = db.execute(
        select(
            UsageRecord.occurred_at,
            UsageRecord.total_tokens,
            UsageRecord.prompt_tokens,
            UsageRecord.completion_tokens,
            UsageRecord.estimated_cost,
            UsageRecord.latency_ms,
            UsageRecord.succeeded,
        ).where(UsageRecord.occurred_at >= since)
    ).all()

    buckets: dict[str, dict] = {}
    for day_offset in range(days, -1, -1):
        day = (datetime.now(timezone.utc) - timedelta(days=day_offset)).date().isoformat()
        buckets[day] = {
            "date": day,
            "requests": 0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "estimated_cost": 0.0,
            "latency_sum": 0,
            "errors": 0,
        }

    for occurred_at, total, prompt, completion, cost, latency, ok in rows:
        key = occurred_at.astimezone(timezone.utc).date().isoformat()
        bucket = buckets.get(key)
        if bucket is None:
            continue
        bucket["requests"] += 1
        bucket["prompt_tokens"] += int(prompt or 0)
        bucket["completion_tokens"] += int(completion or 0)
        bucket["total_tokens"] += int(total or 0)
        bucket["estimated_cost"] += float(cost or 0.0)
        bucket["latency_sum"] += int(latency or 0)
        if not ok:
            bucket["errors"] += 1

    series = []
    for bucket in buckets.values():
        requests = bucket["requests"]
        series.append(
            {
                "date": bucket["date"],
                "requests": requests,
                "prompt_tokens": bucket["prompt_tokens"],
                "completion_tokens": bucket["completion_tokens"],
                "total_tokens": bucket["total_tokens"],
                "estimated_cost": round(bucket["estimated_cost"], 4),
                "avg_latency_ms": int(bucket["latency_sum"] / requests) if requests else 0,
                "error_rate_pct": round(bucket["errors"] / requests * 100, 2) if requests else 0.0,
            }
        )
    return series


def usage_by_dimension(db: Session, column, *, days: int = 30, limit: int = 10) -> list[dict]:
    since = datetime.now(timezone.utc) - timedelta(days=days)
    rows = db.execute(
        select(
            column,
            func.count(UsageRecord.id),
            func.coalesce(func.sum(UsageRecord.total_tokens), 0),
            func.coalesce(func.sum(UsageRecord.estimated_cost), 0.0),
        )
        .where(UsageRecord.occurred_at >= since)
        .group_by(column)
        .order_by(func.coalesce(func.sum(UsageRecord.estimated_cost), 0.0).desc())
        .limit(limit)
    ).all()
    return [
        {
            "key": str(key) if key is not None else "unassigned",
            "requests": int(requests or 0),
            "total_tokens": int(tokens or 0),
            "estimated_cost": round(float(cost or 0.0), 4),
        }
        for key, requests, tokens, cost in rows
    ]


def budget_status(db: Session) -> list[dict]:
    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    results = []
    for budget in db.execute(select(Budget).where(Budget.is_active.is_(True))).scalars():
        since = month_start if budget.scope == "monthly" else now - timedelta(days=1)
        stmt = select(func.coalesce(func.sum(UsageRecord.estimated_cost), 0.0)).where(
            UsageRecord.occurred_at >= since
        )
        if budget.team:
            stmt = stmt.where(UsageRecord.team == budget.team)
        spent = float(db.scalar(stmt) or 0.0)
        ratio = (spent / budget.amount) if budget.amount else 0.0
        results.append(
            {
                "id": str(budget.id),
                "name": budget.name,
                "scope": budget.scope,
                "team": budget.team,
                "amount": budget.amount,
                "currency": budget.currency,
                "spent": round(spent, 4),
                "utilisation_pct": round(ratio * 100, 2),
                "state": (
                    "exceeded"
                    if ratio >= 1
                    else "warning"
                    if ratio >= budget.warning_threshold
                    else "ok"
                ),
            }
        )
    return results
