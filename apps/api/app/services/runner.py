"""Agent run orchestration: execute the graph, then persist the full trace."""

from __future__ import annotations

import time
import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.core.errors import NotFoundError, ValidationError
from app.core.logging import correlation_id_ctx, get_logger
from app.db.models import (
    Agent,
    AgentRun,
    AgentRunStep,
    GuardrailEvent,
    GuardrailPolicy,
    User,
)
from app.providers.registry import provider_summary
from app.services import costs
from app.services.agent_graph import build_graph

logger = get_logger(__name__)


def _resolve_policy(db: Session, agent: Agent) -> GuardrailPolicy | None:
    if agent.guardrail_policy_id:
        policy = db.get(GuardrailPolicy, agent.guardrail_policy_id)
        if policy and policy.deleted_at is None:
            return policy
    return (
        db.query(GuardrailPolicy)
        .filter(GuardrailPolicy.is_default.is_(True), GuardrailPolicy.deleted_at.is_(None))
        .first()
    )


def execute_agent(
    db: Session,
    agent: Agent,
    question: str,
    *,
    user: User | None = None,
    correlation_id: str | None = None,
    tool_args: dict[str, Any] | None = None,
) -> AgentRun:
    if agent.deleted_at is not None:
        raise NotFoundError("Agent not found.")
    if not agent.enabled:
        raise ValidationError("Agent is disabled. Enable it before running.")

    policy = _resolve_policy(db, agent)
    graph = build_graph(db, agent, policy)
    correlation_id = correlation_id or correlation_id_ctx.get() or uuid.uuid4().hex

    run = AgentRun(
        agent_id=agent.id,
        agent_version=agent.current_version,
        user_id=user.id if user else None,
        correlation_id=correlation_id,
        status="running",
        input_text=question,
        model_name=agent.model.name if agent.model else "local-grounded",
    )
    db.add(run)
    db.flush()

    started = time.perf_counter()
    try:
        state = graph.invoke(
            {
                "question": question,
                "agent_id": str(agent.id),
                "correlation_id": correlation_id,
                "tool_args": tool_args or {},
                "steps": [],
                "findings": [],
            }
        )
    except Exception as exc:
        run.status = "failed"
        run.error_code = "graph_error"
        run.error_message = str(exc)[:500]
        run.latency_ms = int((time.perf_counter() - started) * 1000)
        db.flush()
        logger.exception("agent_run_failed", extra={"run_id": str(run.id)})
        return run

    latency_ms = int((time.perf_counter() - started) * 1000)

    run.status = state.get("status", "succeeded")
    run.output_text = state.get("answer") or ""
    run.model_name = state.get("model_name") or run.model_name
    run.used_fallback = bool(state.get("used_fallback"))
    run.prompt_tokens = int(state.get("prompt_tokens", 0))
    run.completion_tokens = int(state.get("completion_tokens", 0))
    run.total_tokens = run.prompt_tokens + run.completion_tokens
    run.latency_ms = latency_ms
    run.error_code = state.get("error_code")
    run.error_message = state.get("error_message")
    run.guardrail_outcome = state.get("guardrail_outcome", "pass")
    run.citations = state.get("citations") or []
    run.trace = {
        "route": state.get("route"),
        "retrieval": state.get("retrieval") or {},
        "tool_results": state.get("tool_results") or [],
        "attempts": state.get("attempts", 0),
        "providers": provider_summary(),
        "correlation_id": correlation_id,
    }

    for index, step in enumerate(state.get("steps") or []):
        db.add(
            AgentRunStep(
                run_id=run.id,
                step_index=index,
                node=step.get("node", "unknown"),
                status=step.get("status", "ok"),
                duration_ms=int(step.get("duration_ms", 0)),
                detail=step.get("detail") or {},
            )
        )

    for finding in state.get("findings") or []:
        db.add(
            GuardrailEvent(
                run_id=run.id,
                policy_id=policy.id if policy else None,
                stage=finding.get("stage", "input"),
                rule=finding.get("rule", "unknown"),
                severity=finding.get("severity", "low"),
                action="blocked" if run.status == "blocked" else "flagged",
                detail=finding.get("detail") or {},
            )
        )

    model = agent.model
    if run.total_tokens:
        usage = costs.record_usage(
            db,
            model=model,
            model_name=run.model_name or "local-grounded",
            prompt_tokens=run.prompt_tokens,
            completion_tokens=run.completion_tokens,
            latency_ms=latency_ms,
            run_id=run.id,
            agent_id=agent.id,
            user_id=user.id if user else None,
            team=user.team if user else None,
            succeeded=run.status == "succeeded",
        )
        run.estimated_cost = usage.estimated_cost

    db.flush()
    logger.info(
        "agent_run_completed",
        extra={
            "run_id": str(run.id),
            "agent": agent.slug,
            "status": run.status,
            "latency_ms": latency_ms,
            "tokens": run.total_tokens,
            "citations": len(run.citations),
        },
    )
    return run
