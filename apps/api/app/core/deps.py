"""Authentication and authorization dependencies."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Annotated

from fastapi import Depends, Header, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.errors import AuthenticationError, PermissionDeniedError
from app.core.rbac import Role, has_permission, permissions_for
from app.core.security import decode_access_token, hash_api_key
from app.db.models import ApiKey, User

bearer_scheme = HTTPBearer(auto_error=False, description="JWT access token")

DbSession = Annotated[Session, Depends(get_db)]


def _user_from_token(db: Session, token: str) -> User:
    payload = decode_access_token(token)
    try:
        user_id = uuid.UUID(payload["sub"])
    except (KeyError, ValueError) as exc:
        raise AuthenticationError("Malformed access token.") from exc
    user = db.get(User, user_id)
    if user is None or not user.is_active or user.deleted_at is not None:
        raise AuthenticationError("Account is inactive or no longer exists.")
    return user


def _user_from_api_key(db: Session, raw_key: str) -> User:
    record = db.execute(
        select(ApiKey).where(ApiKey.key_hash == hash_api_key(raw_key))
    ).scalar_one_or_none()
    now = datetime.now(timezone.utc)
    if record is None or record.revoked_at is not None:
        raise AuthenticationError("Invalid API key.")
    if record.expires_at and record.expires_at < now:
        raise AuthenticationError("API key has expired.")
    user = db.get(User, record.user_id)
    if user is None or not user.is_active or user.deleted_at is not None:
        raise AuthenticationError("Account is inactive or no longer exists.")
    record.last_used_at = now
    db.flush()
    return user


def get_current_user(
    request: Request,
    db: DbSession,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)] = None,
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
) -> User:
    """Accept either a bearer JWT (UI) or an X-API-Key header (CI/CD)."""
    if credentials and credentials.credentials:
        user = _user_from_token(db, credentials.credentials)
    elif x_api_key:
        user = _user_from_api_key(db, x_api_key)
    else:
        raise AuthenticationError("Authentication required.")
    request.state.user_email = user.email
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_permission(permission: str) -> Callable[[User], User]:
    """Route dependency factory: `Depends(require_permission("agents:write"))`."""

    def _dependency(user: CurrentUser) -> User:
        if not has_permission(user.role, permission):
            raise PermissionDeniedError(
                f"Role '{user.role}' is not allowed to perform '{permission}'."
            )
        return user

    return _dependency


def require_role(*roles: Role) -> Callable[[User], User]:
    allowed = {role.value for role in roles}

    def _dependency(user: CurrentUser) -> User:
        if user.role not in allowed:
            raise PermissionDeniedError("Insufficient role for this operation.")
        return user

    return _dependency


def current_permissions(user: User) -> list[str]:
    return sorted(permissions_for(user.role))
