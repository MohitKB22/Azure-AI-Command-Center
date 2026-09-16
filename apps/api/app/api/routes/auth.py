"""Authentication, session and API key endpoints."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy import select

from app.core.config import settings
from app.core.deps import CurrentUser, DbSession, current_permissions, require_permission
from app.core.errors import AuthenticationError, NotFoundError
from app.core.security import create_access_token, generate_api_key, verify_password
from app.db.models import ApiKey, User
from app.schemas import (
    ApiKeyCreate,
    ApiKeyCreated,
    ApiKeyOut,
    LoginRequest,
    MeResponse,
    TokenResponse,
    UserOut,
)
from app.services import audit

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, request: Request, db: DbSession) -> TokenResponse:
    user = db.execute(
        select(User).where(User.email == payload.email.lower())
    ).scalar_one_or_none()

    # Same error for unknown user and wrong password: no account enumeration.
    if user is None or not verify_password(payload.password, user.hashed_password):
        audit.record(
            db,
            action="auth.login",
            resource_type="user",
            resource_id=payload.email,
            outcome="failure",
            ip_address=request.client.host if request.client else None,
        )
        db.commit()
        raise AuthenticationError("Incorrect email or password.")

    if not user.is_active or user.deleted_at is not None:
        raise AuthenticationError("This account is disabled.")

    token, expires_at = create_access_token(user.id, role=user.role)
    user.last_login_at = datetime.now(timezone.utc)
    audit.record(
        db,
        action="auth.login",
        resource_type="user",
        resource_id=user.id,
        actor=user,
        ip_address=request.client.host if request.client else None,
    )
    db.commit()
    return TokenResponse(
        access_token=token,
        expires_at=expires_at,
        user=UserOut.model_validate(user),
    )


@router.get("/me", response_model=MeResponse)
def me(user: CurrentUser) -> MeResponse:
    return MeResponse(
        user=UserOut.model_validate(user),
        permissions=current_permissions(user),
        demo_mode=settings.demo_mode,
        environment=settings.environment,
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(user: CurrentUser, db: DbSession) -> None:
    """Client-side token disposal.

    Access tokens are short-lived and stateless, so there is nothing to revoke
    server-side. The event is still audited.
    """
    audit.record(db, action="auth.logout", resource_type="user", resource_id=user.id, actor=user)
    db.commit()


@router.get("/api-keys", response_model=list[ApiKeyOut])
def list_api_keys(user: CurrentUser, db: DbSession) -> list[ApiKey]:
    return list(
        db.execute(
            select(ApiKey).where(ApiKey.user_id == user.id).order_by(ApiKey.created_at.desc())
        )
        .scalars()
        .all()
    )


@router.post("/api-keys", response_model=ApiKeyCreated, status_code=status.HTTP_201_CREATED)
def create_api_key(
    payload: ApiKeyCreate,
    db: DbSession,
    user: User = Depends(require_permission("settings:write")),
) -> ApiKeyCreated:
    raw_key, prefix, key_hash = generate_api_key()
    record = ApiKey(
        user_id=user.id,
        name=payload.name,
        key_prefix=prefix,
        key_hash=key_hash,
        expires_at=(
            datetime.now(timezone.utc) + timedelta(days=payload.expires_in_days)
            if payload.expires_in_days
            else None
        ),
    )
    db.add(record)
    audit.record(
        db,
        action="api_key.create",
        resource_type="api_key",
        resource_id=record.id,
        actor=user,
        changes={"name": payload.name},
    )
    db.commit()
    db.refresh(record)
    # The plaintext key is returned exactly once and never persisted.
    return ApiKeyCreated(api_key=ApiKeyOut.model_validate(record), key=raw_key)


@router.delete("/api-keys/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_api_key(key_id: uuid.UUID, user: CurrentUser, db: DbSession) -> None:
    record = db.get(ApiKey, key_id)
    if record is None or record.user_id != user.id:
        raise NotFoundError("API key not found.")
    record.revoked_at = datetime.now(timezone.utc)
    audit.record(
        db, action="api_key.revoke", resource_type="api_key", resource_id=key_id, actor=user
    )
    db.commit()
