"""Managed Identity / Entra ID token acquisition.

Isolated so the rest of the codebase never imports azure-identity directly and
local mode never needs the Azure SDK installed.
"""

from __future__ import annotations

import time

from app.core.errors import ProviderNotConfiguredError

_COGNITIVE_SCOPE = "https://cognitiveservices.azure.com/.default"
_cache: dict[str, tuple[str, float]] = {}


def managed_identity_token(scope: str = _COGNITIVE_SCOPE) -> str:
    """Fetch (and briefly cache) an Entra ID access token via DefaultAzureCredential."""
    cached = _cache.get(scope)
    if cached and cached[1] - 60 > time.time():
        return cached[0]

    try:
        from azure.identity import DefaultAzureCredential
    except ImportError as exc:  # pragma: no cover - depends on optional extra
        raise ProviderNotConfiguredError(
            "azure-identity is not installed. Install the 'azure' extra: "
            "pip install -e '.[azure]'"
        ) from exc

    credential = DefaultAzureCredential()
    token = credential.get_token(scope)
    _cache[scope] = (token.token, float(token.expires_on))
    return token.token
