"""Raw document storage: local filesystem for development, Blob Storage for Azure."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.core.errors import NotFoundError, ProviderError, ProviderNotConfiguredError


class LocalBlobStore:
    name = "local"

    def __init__(self, root: str | None = None):
        self.root = Path(root or settings.local_blob_dir).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        # Prevent path traversal: the resolved path must stay under root.
        candidate = (self.root / key.lstrip("/")).resolve()
        if not str(candidate).startswith(str(self.root)):
            raise ProviderError("Invalid storage key.")
        return candidate

    def put(self, key: str, data: bytes, content_type: str) -> str:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return f"file://{path}"

    def get(self, key: str) -> bytes:
        path = self._path(key)
        if not path.exists():
            raise NotFoundError(f"Stored object '{key}' was not found.")
        return path.read_bytes()

    def delete(self, key: str) -> None:
        path = self._path(key)
        if path.exists():
            path.unlink()

    def health(self) -> dict[str, Any]:
        writable = os.access(self.root, os.W_OK)
        return {
            "provider": "local",
            "status": "healthy" if writable else "unhealthy",
            "root": str(self.root),
        }


class AzureBlobStore:
    """Azure Blob Storage via azure-storage-blob (API key-free, identity first)."""

    name = "azure"

    def __init__(self) -> None:
        if not settings.azure_storage_account_url:
            raise ProviderNotConfiguredError("AZURE_STORAGE_ACCOUNT_URL is required.")
        try:
            from azure.identity import DefaultAzureCredential
            from azure.storage.blob import BlobServiceClient
        except ImportError as exc:  # pragma: no cover - optional extra
            raise ProviderNotConfiguredError(
                "azure-storage-blob is not installed. Install the 'azure' extra."
            ) from exc

        self._service = BlobServiceClient(
            account_url=settings.azure_storage_account_url,
            credential=DefaultAzureCredential(),
        )
        self._container = settings.azure_storage_container

    def put(self, key: str, data: bytes, content_type: str) -> str:
        from azure.storage.blob import ContentSettings

        client = self._service.get_blob_client(self._container, key)
        client.upload_blob(
            data, overwrite=True, content_settings=ContentSettings(content_type=content_type)
        )
        return client.url

    def get(self, key: str) -> bytes:
        client = self._service.get_blob_client(self._container, key)
        return client.download_blob().readall()

    def delete(self, key: str) -> None:
        client = self._service.get_blob_client(self._container, key)
        client.delete_blob(delete_snapshots="include")

    def health(self) -> dict[str, Any]:
        try:
            container = self._service.get_container_client(self._container)
            container.get_container_properties()
            return {"provider": "azure", "status": "healthy", "container": self._container}
        except Exception as exc:  # pragma: no cover - depends on live service
            return {"provider": "azure", "status": "unhealthy", "detail": str(exc)}
