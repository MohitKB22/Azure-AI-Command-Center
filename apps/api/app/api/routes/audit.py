"""Audit log access. Read-only by design — entries are never edited."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy import or_, select

from app.core.deps import DbSession, require_permission
from app.core.pagination import Page, PageParams, apply_sort, page_params, paginate
from app.db.models import AuditLog, User
from app.schemas import AuditLogOut

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("/logs", response_model=Page[AuditLogOut])
def list_logs(
    db: DbSession,
    params: PageParams = Depends(page_params),
    action: str | None = None,
    resource_type: str | None = None,
    outcome: str | None = None,
    since: datetime | None = None,
    _: User = Depends(require_permission("audit:read")),
) -> Page[AuditLogOut]:
    stmt = select(AuditLog)
    if action:
        stmt = stmt.where(AuditLog.action == action)
    if resource_type:
        stmt = stmt.where(AuditLog.resource_type == resource_type)
    if outcome:
        stmt = stmt.where(AuditLog.outcome == outcome)
    if since:
        stmt = stmt.where(AuditLog.created_at >= since)
    if params.q:
        needle = f"%{params.q.lower()}%"
        stmt = stmt.where(
            or_(
                AuditLog.actor_email.ilike(needle),
                AuditLog.action.ilike(needle),
                AuditLog.resource_id.ilike(needle),
            )
        )
    stmt = apply_sort(stmt, AuditLog, params, "created_at")
    rows, total = paginate(db, stmt, params)
    return Page.build([AuditLogOut.model_validate(row) for row in rows], total, params)


@router.get("/actions", response_model=list[str])
def list_actions(
    db: DbSession,
    _: User = Depends(require_permission("audit:read")),
) -> list[str]:
    return [
        row[0]
        for row in db.execute(select(AuditLog.action).distinct().order_by(AuditLog.action)).all()
    ]
