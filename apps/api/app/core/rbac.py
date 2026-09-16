"""Role-based access control.

Permissions are `<resource>:<action>` strings. Roles are static bundles of
permissions so authorization decisions never require a database round-trip.
"""

from __future__ import annotations

from enum import Enum


class Role(str, Enum):
    ADMIN = "admin"
    AI_ENGINEER = "ai_engineer"
    DEVELOPER = "developer"
    ANALYST = "analyst"
    VIEWER = "viewer"


RESOURCES = (
    "agents",
    "models",
    "prompts",
    "documents",
    "evaluations",
    "monitoring",
    "costs",
    "settings",
    "users",
    "audit",
    "guardrails",
)
ACTIONS = ("read", "write", "delete", "execute")


def _all_permissions() -> set[str]:
    return {f"{resource}:{action}" for resource in RESOURCES for action in ACTIONS}


def _read_only() -> set[str]:
    return {f"{resource}:read" for resource in RESOURCES} - {"users:read", "audit:read"}


ROLE_PERMISSIONS: dict[Role, set[str]] = {
    Role.ADMIN: _all_permissions(),
    Role.AI_ENGINEER: _read_only()
    | {
        "agents:write",
        "agents:execute",
        "agents:delete",
        "models:write",
        "prompts:write",
        "prompts:execute",
        "documents:write",
        "documents:delete",
        "evaluations:write",
        "evaluations:execute",
        "guardrails:write",
        "audit:read",
    },
    Role.DEVELOPER: _read_only()
    | {
        "agents:write",
        "agents:execute",
        "prompts:write",
        "prompts:execute",
        "documents:write",
        "evaluations:execute",
    },
    Role.ANALYST: _read_only() | {"evaluations:execute", "audit:read"},
    Role.VIEWER: _read_only(),
}

ROLE_LABELS: dict[Role, str] = {
    Role.ADMIN: "Admin",
    Role.AI_ENGINEER: "AI Engineer",
    Role.DEVELOPER: "Developer",
    Role.ANALYST: "Analyst",
    Role.VIEWER: "Viewer",
}


def permissions_for(role: Role | str) -> set[str]:
    try:
        return set(ROLE_PERMISSIONS[Role(role)])
    except ValueError:
        return set()


def has_permission(role: Role | str, permission: str) -> bool:
    return permission in permissions_for(role)
