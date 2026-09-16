"""Guardrail policy management, testing and event history."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy import select

from app.core.db import utcnow
from app.core.deps import DbSession, require_permission
from app.core.errors import ConflictError, NotFoundError
from app.core.pagination import Page, PageParams, apply_sort, page_params, paginate
from app.db.models import GuardrailEvent, GuardrailPolicy, User
from app.schemas import (
    GuardrailEventOut,
    GuardrailFindingOut,
    GuardrailPolicyCreate,
    GuardrailPolicyOut,
    GuardrailTestRequest,
    GuardrailTestResponse,
)
from app.services import audit
from app.services import guardrails as gr

router = APIRouter(prefix="/guardrails", tags=["guardrails"])


@router.get("/policies", response_model=list[GuardrailPolicyOut])
def list_policies(
    db: DbSession,
    _: User = Depends(require_permission("guardrails:read")),
) -> list[GuardrailPolicy]:
    return list(
        db.execute(
            select(GuardrailPolicy)
            .where(GuardrailPolicy.deleted_at.is_(None))
            .order_by(GuardrailPolicy.is_default.desc(), GuardrailPolicy.name.asc())
        )
        .scalars()
        .all()
    )


@router.get("/rules")
def list_rules(_: User = Depends(require_permission("guardrails:read"))) -> dict:
    """Expose the detection catalogue so the UI can explain what is enforced."""
    return {
        "injection_rules": [
            {"rule": rule, "severity": severity} for rule, _, severity in gr.INJECTION_PATTERNS
        ],
        "pii_rules": [{"rule": f"pii_{rule}"} for rule, _ in gr.PII_PATTERNS],
        "disclaimer": (
            "These are heuristic detections, not a complete security boundary. "
            "Layer them with Azure AI Content Safety and least-privilege tool design."
        ),
    }


@router.post("/policies", response_model=GuardrailPolicyOut, status_code=status.HTTP_201_CREATED)
def create_policy(
    payload: GuardrailPolicyCreate,
    db: DbSession,
    user: User = Depends(require_permission("guardrails:write")),
) -> GuardrailPolicy:
    if db.execute(
        select(GuardrailPolicy).where(
            GuardrailPolicy.name == payload.name, GuardrailPolicy.deleted_at.is_(None)
        )
    ).scalar_one_or_none():
        raise ConflictError("A policy with that name already exists.")

    if payload.is_default:
        for existing in db.execute(
            select(GuardrailPolicy).where(GuardrailPolicy.is_default.is_(True))
        ).scalars():
            existing.is_default = False

    policy = GuardrailPolicy(**payload.model_dump())
    db.add(policy)
    audit.record(
        db,
        action="guardrail_policy.create",
        resource_type="guardrail_policy",
        resource_id=policy.id,
        actor=user,
        changes={"name": policy.name},
    )
    db.commit()
    db.refresh(policy)
    return policy


@router.delete("/policies/{policy_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_policy(
    policy_id: uuid.UUID,
    db: DbSession,
    user: User = Depends(require_permission("guardrails:delete")),
) -> None:
    policy = db.get(GuardrailPolicy, policy_id)
    if policy is None or policy.deleted_at is not None:
        raise NotFoundError("Policy not found.")
    policy.deleted_at = utcnow()
    audit.record(
        db,
        action="guardrail_policy.delete",
        resource_type="guardrail_policy",
        resource_id=policy.id,
        actor=user,
    )
    db.commit()


@router.post("/test", response_model=GuardrailTestResponse)
def test_guardrail(
    payload: GuardrailTestRequest,
    db: DbSession,
    _: User = Depends(require_permission("guardrails:read")),
) -> GuardrailTestResponse:
    policy = None
    if payload.policy_id:
        policy = db.get(GuardrailPolicy, payload.policy_id)
        if policy is None or policy.deleted_at is not None:
            raise NotFoundError("Policy not found.")
    else:
        policy = db.execute(
            select(GuardrailPolicy).where(
                GuardrailPolicy.is_default.is_(True), GuardrailPolicy.deleted_at.is_(None)
            )
        ).scalar_one_or_none()

    decision = (
        gr.evaluate_input(payload.text, policy)
        if payload.stage == "input"
        else gr.evaluate_output(payload.text, policy)
    )
    return GuardrailTestResponse(
        action=decision.action,
        outcome=decision.outcome,
        text=decision.text,
        findings=[
            GuardrailFindingOut(rule=f.rule, severity=f.severity, detail=f.detail)
            for f in decision.findings
        ],
    )


@router.get("/events", response_model=Page[GuardrailEventOut])
def list_events(
    db: DbSession,
    params: PageParams = Depends(page_params),
    severity: str | None = None,
    _: User = Depends(require_permission("guardrails:read")),
) -> Page[GuardrailEventOut]:
    stmt = select(GuardrailEvent)
    if severity:
        stmt = stmt.where(GuardrailEvent.severity == severity)
    if params.q:
        stmt = stmt.where(GuardrailEvent.rule.ilike(f"%{params.q.lower()}%"))
    stmt = apply_sort(stmt, GuardrailEvent, params, "created_at")
    rows, total = paginate(db, stmt, params)
    return Page.build([GuardrailEventOut.model_validate(row) for row in rows], total, params)
