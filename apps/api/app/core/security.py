"""Password hashing, API-key hashing and JWT issuing/verification."""

from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings
from app.core.errors import AuthenticationError

ALGORITHM = "HS256"

# pbkdf2_sha256 is the default because it is pure-Python and therefore behaves
# identically across every environment we run in. bcrypt hashes are still
# verifiable so existing credentials keep working after a backend change.
pwd_context = CryptContext(
    schemes=["pbkdf2_sha256", "bcrypt"],
    deprecated="auto",
    pbkdf2_sha256__rounds=390_000,
)


def hash_password(password: str) -> str:
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters long.")
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return pwd_context.verify(password, password_hash)
    except ValueError:
        return False


def generate_api_key() -> tuple[str, str, str]:
    """Return (plaintext_key, key_prefix, key_hash). Plaintext is shown once."""
    raw = secrets.token_urlsafe(32)
    key = f"aicc_{raw}"
    return key, key[:12], hash_api_key(key)


def hash_api_key(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def verify_api_key(key: str, key_hash: str) -> bool:
    return hmac.compare_digest(hash_api_key(key), key_hash)


def create_access_token(
    subject: str | uuid.UUID,
    *,
    role: str,
    expires_minutes: int | None = None,
    extra: dict[str, Any] | None = None,
) -> tuple[str, datetime]:
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=expires_minutes or settings.access_token_ttl_minutes
    )
    payload: dict[str, Any] = {
        "sub": str(subject),
        "role": role,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "jti": secrets.token_hex(8),
        "iss": settings.app_name,
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM), expire


def decode_access_token(token: str) -> dict[str, Any]:
    try:
        return jwt.decode(
            token,
            settings.secret_key,
            algorithms=[ALGORITHM],
            options={"require_sub": True, "require_exp": True},
        )
    except JWTError as exc:
        raise AuthenticationError("Invalid or expired credentials.") from exc
