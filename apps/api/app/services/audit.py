"""Audit trail writer. Every mutation flows through here."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.core.logging import get_logger, redact, request_id_ctx
from app.db.models import AuditLog, User

logger = get_logger(__name__)


def record(
    db: Session,
    *,
    action: str,
    resource_type: str,
    resource_id: str | uuid.UUID | None = None,
    actor: User | None = None,
    outcome: str = "success",
    changes: dict[str, Any] | None = None,
    ip_address: str | None = None,
) -> AuditLog:
    entry = AuditLog(
        actor_id=actor.id if actor else None,
        actor_email=actor.email if actor else None,
        action=action,
        resource_type=resource_type,
        resource_id=str(resource_id) if resource_id else None,
        outcome=outcome,
        ip_address=ip_address,
        request_id=request_id_ctx.get(),
        changes=redact(changes or {}),
    )
    db.add(entry)
    db.flush()
    logger.info(
        "audit",
        extra={
            "action": action,
            "resource_type": resource_type,
            "resource_id": entry.resource_id,
            "outcome": outcome,
            "actor": entry.actor_email,
        },
    )
    return entry


def diff(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    """Field-level change set, with secrets stripped."""
    changed: dict[str, Any] = {}
    for key, new_value in after.items():
        old_value = before.get(key)
        if old_value != new_value:
            changed[key] = {"from": old_value, "to": new_value}
    return redact(changed)
