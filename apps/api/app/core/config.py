"""Application configuration.

All configuration is environment driven. No secret ever has a usable default:
local development runs against deterministic in-process providers instead.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["local", "dev", "staging", "production"]
ProviderMode = Literal["local", "azure"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ---- app ----
    app_name: str = "Azure AI Command Center"
    environment: Environment = "local"
    api_v1_prefix: str = "/api/v1"
    debug: bool = False

    # Demo mode seeds and labels synthetic data. Must be off in production.
    demo_mode: bool = True

    # ---- security ----
    # Dev-only fallback key. `Settings.validate_production()` rejects it outside local.
    secret_key: str = "dev-insecure-key-change-me"
    access_token_ttl_minutes: int = 60 * 8
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])
    rate_limit_per_minute: int = 240
    max_upload_bytes: int = 20 * 1024 * 1024
    allowed_upload_extensions: list[str] = Field(
        default_factory=lambda: [".pdf", ".txt", ".md", ".csv", ".json", ".docx"]
    )

    # ---- storage ----
    database_url: str = "sqlite:///./azure_ai_command_center.db"
    sql_echo: bool = False

    # ---- provider selection ----
    llm_provider: ProviderMode = "local"
    embedding_provider: ProviderMode = "local"
    vector_store: Literal["local", "qdrant"] = "local"
    blob_provider: ProviderMode = "local"
    local_blob_dir: str = "./var/blobs"

    # ---- azure (only read when the matching provider is set to "azure") ----
    azure_openai_endpoint: str | None = None
    azure_openai_api_key: str | None = None
    azure_openai_api_version: str = "2024-10-21"
    azure_openai_chat_deployment: str | None = None
    azure_openai_embedding_deployment: str | None = None
    azure_search_endpoint: str | None = None
    azure_search_api_key: str | None = None
    azure_storage_account_url: str | None = None
    azure_storage_container: str = "documents"
    azure_keyvault_url: str | None = None
    azure_use_managed_identity: bool = False
    applicationinsights_connection_string: str | None = None

    # ---- qdrant ----
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str | None = None
    qdrant_collection: str = "aicc_chunks"

    # ---- rag defaults ----
    embedding_dim: int = 768
    default_chunk_size: int = 900
    default_chunk_overlap: int = 150
    default_top_k: int = 5
    default_similarity_threshold: float = 0.05

    @field_validator("cors_origins", "allowed_upload_extensions", mode="before")
    @classmethod
    def _split_csv(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @property
    def is_local(self) -> bool:
        return self.environment == "local"

    def validate_production(self) -> list[str]:
        """Return blocking misconfigurations for non-local environments."""
        problems: list[str] = []
        if self.environment == "local":
            return problems
        if self.secret_key == "dev-insecure-key-change-me" or len(self.secret_key) < 32:
            problems.append("SECRET_KEY must be set to a unique value of at least 32 characters.")
        if self.database_url.startswith("sqlite"):
            problems.append("DATABASE_URL must point at PostgreSQL outside local development.")
        if self.llm_provider == "azure" and not self.azure_openai_endpoint:
            problems.append("AZURE_OPENAI_ENDPOINT is required when LLM_PROVIDER=azure.")
        if self.llm_provider == "azure" and not self.azure_openai_chat_deployment:
            problems.append("AZURE_OPENAI_CHAT_DEPLOYMENT is required when LLM_PROVIDER=azure.")
        if (
            self.llm_provider == "azure"
            and not self.azure_openai_api_key
            and not self.azure_use_managed_identity
        ):
            problems.append(
                "Either AZURE_OPENAI_API_KEY or AZURE_USE_MANAGED_IDENTITY is required."
            )
        if self.environment == "production" and self.demo_mode:
            problems.append("DEMO_MODE must be false in production.")
        return problems


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
