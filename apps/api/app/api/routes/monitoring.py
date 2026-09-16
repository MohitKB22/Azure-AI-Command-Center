"""Azure service monitor, alerts and system health dashboards."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select

from app.core.db import utcnow
from app.core.deps import DbSession, require_permission
from app.core.errors import NotFoundError
from app.core.pagination import Page, PageParams, apply_sort, page_params, paginate
from app.db.models import Alert, AzureResource, User
from app.schemas import AlertOut, AzureResourceOut
from app.services import audit
from app.services.monitoring import get_collector, system_health

router = APIRouter(prefix="/monitoring", tags=["monitoring"])


@router.get("/azure-resources", response_model=list[AzureResourceOut])
def list_resources(
    db: DbSession,
    _: User = Depends(require_permission("monitoring:read")),
) -> list[AzureResource]:
    return list(
        db.execute(select(AzureResource).order_by(AzureResource.name.asc())).scalars().all()
    )


@router.post("/collect", response_model=list[AzureResourceOut])
def collect_metrics(
    db: DbSession,
    user: User = Depends(require_permission("monitoring:write")),
) -> list[AzureResource]:
    """Run the active collector once and persist the results.

    In production this is driven by a scheduled worker; the endpoint exists so
    the UI can force a refresh and so CI can assert the collector runs.
    """
    collector = get_collector()
    collector.collect(db)
    audit.record(
        db,
        action="monitoring.collect",
        resource_type="azure_resource",
        actor=user,
        changes={"collector": collector.name},
    )
    db.commit()
    return list(
        db.execute(select(AzureResource).order_by(AzureResource.name.asc())).scalars().all()
    )


@router.get("/health")
def health(
    db: DbSession,
    _: User = Depends(require_permission("monitoring:read")),
) -> dict:
    return system_health(db)


@router.get("/alerts", response_model=Page[AlertOut])
def list_alerts(
    db: DbSession,
    params: PageParams = Depends(page_params),
    status_filter: str | None = None,
    severity: str | None = None,
    _: User = Depends(require_permission("monitoring:read")),
) -> Page[AlertOut]:
    stmt = select(Alert)
    if status_filter:
        stmt = stmt.where(Alert.status == status_filter)
    if severity:
        stmt = stmt.where(Alert.severity == severity)
    if params.q:
        stmt = stmt.where(Alert.title.ilike(f"%{params.q.lower()}%"))
    stmt = apply_sort(stmt, Alert, params, "created_at")
    rows, total = paginate(db, stmt, params)
    return Page.build([AlertOut.model_validate(row) for row in rows], total, params)


@router.post("/alerts/{alert_id}/acknowledge", response_model=AlertOut)
def acknowledge(
    alert_id: uuid.UUID,
    db: DbSession,
    user: User = Depends(require_permission("monitoring:write")),
) -> Alert:
    alert = db.get(Alert, alert_id)
    if alert is None:
        raise NotFoundError("Alert not found.")
    alert.status = "acknowledged"
    alert.acknowledged_by = user.id
    alert.acknowledged_at = utcnow()
    audit.record(
        db, action="alert.acknowledge", resource_type="alert", resource_id=alert.id, actor=user
    )
    db.commit()
    db.refresh(alert)
    return alert


@router.post("/alerts/{alert_id}/resolve", response_model=AlertOut)
def resolve(
    alert_id: uuid.UUID,
    db: DbSession,
    user: User = Depends(require_permission("monitoring:write")),
) -> Alert:
    alert = db.get(Alert, alert_id)
    if alert is None:
        raise NotFoundError("Alert not found.")
    alert.status = "resolved"
    alert.resolved_at = utcnow()
    audit.record(
        db, action="alert.resolve", resource_type="alert", resource_id=alert.id, actor=user
    )
    db.commit()
    db.refresh(alert)
    return alert
