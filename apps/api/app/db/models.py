"""SQLAlchemy 2.x ORM models for the control plane.

Conventions: UUID primary keys, timezone-aware timestamps, explicit indexes on
every foreign key and on the columns the UI filters by, and soft delete
(`deleted_at`) on the entities users can remove but auditors still need.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import GUID, Base, UTCDateTime, utcnow


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime, default=utcnow, onupdate=utcnow, nullable=False
    )


class SoftDeleteMixin:
    deleted_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True, index=True)

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None


# --------------------------------------------------------------------------- identity


class User(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(GUID, primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False, index=True)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False, default="viewer", index=True)
    team: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)

    api_keys: Mapped[list[ApiKey]] = relationship(back_populates="user")


class ApiKey(Base, TimestampMixin):
    __tablename__ = "api_keys"

    id: Mapped[uuid.UUID] = mapped_column(GUID, primary_key=True, default=_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    key_prefix: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    key_hash: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    scopes: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)

    user: Mapped[User] = relationship(back_populates="api_keys")


# --------------------------------------------------------------------------- catalog


class ModelCatalogEntry(Base, TimestampMixin, SoftDeleteMixin):
    """A model the platform is allowed to call, plus its cost configuration."""

    __tablename__ = "models"
    __table_args__ = (
        UniqueConstraint("provider", "deployment_name", name="uq_model_provider_deployment"),
        CheckConstraint("context_window > 0", name="ck_model_context_window"),
    )

    id: Mapped[uuid.UUID] = mapped_column(GUID, primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(60), nullable=False, default="azure_openai")
    deployment_name: Mapped[str] = mapped_column(String(120), nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False, default="chat")  # chat|embedding
    context_window: Mapped[int] = mapped_column(Integer, nullable=False, default=8192)
    max_output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=4096)
    capabilities: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    # Cost is configuration, never hard-coded in the pricing service.
    input_cost_per_1k: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    output_cost_per_1k: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="available", index=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_fallback: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class Prompt(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "prompts"

    id: Mapped[uuid.UUID] = mapped_column(GUID, primary_key=True, default=_uuid)
    key: Mapped[str] = mapped_column(String(120), nullable=False, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    active_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    versions: Mapped[list[PromptVersion]] = relationship(
        back_populates="prompt", cascade="all, delete-orphan", order_by="PromptVersion.version"
    )


class PromptVersion(Base, TimestampMixin):
    __tablename__ = "prompt_versions"
    __table_args__ = (UniqueConstraint("prompt_id", "version", name="uq_prompt_version"),)

    id: Mapped[uuid.UUID] = mapped_column(GUID, primary_key=True, default=_uuid)
    prompt_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("prompts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    template: Mapped[str] = mapped_column(Text, nullable=False)
    variables: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    environment: Mapped[str] = mapped_column(String(20), nullable=False, default="development")
    approval_status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    changelog: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        GUID, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    prompt: Mapped[Prompt] = relationship(back_populates="versions")


# --------------------------------------------------------------------------- agents


class Agent(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "agents"

    id: Mapped[uuid.UUID] = mapped_column(GUID, primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    slug: Mapped[str] = mapped_column(String(200), nullable=False, unique=True, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft", index=True)
    environment: Mapped[str] = mapped_column(
        String(20), nullable=False, default="development", index=True
    )
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    system_prompt: Mapped[str] = mapped_column(Text, nullable=False, default="")
    model_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID, ForeignKey("models.id", ondelete="SET NULL"), nullable=True, index=True
    )
    fallback_model_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID, ForeignKey("models.id", ondelete="SET NULL"), nullable=True
    )
    temperature: Mapped[float] = mapped_column(Float, nullable=False, default=0.2)
    max_output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=800)
    timeout_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=60)
    max_retries: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    tools: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    memory_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    rag_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    rag_pipeline_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID, ForeignKey("rag_pipelines.id", ondelete="SET NULL"), nullable=True, index=True
    )
    guardrail_policy_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID, ForeignKey("guardrail_policies.id", ondelete="SET NULL"), nullable=True
    )
    current_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        GUID, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        GUID, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    model: Mapped[ModelCatalogEntry | None] = relationship(foreign_keys=[model_id], lazy="joined")
    fallback_model: Mapped[ModelCatalogEntry | None] = relationship(
        foreign_keys=[fallback_model_id]
    )
    versions: Mapped[list[AgentVersion]] = relationship(
        back_populates="agent", cascade="all, delete-orphan", order_by="AgentVersion.version"
    )
    runs: Mapped[list[AgentRun]] = relationship(back_populates="agent")


class AgentVersion(Base, TimestampMixin):
    __tablename__ = "agent_versions"
    __table_args__ = (UniqueConstraint("agent_id", "version", name="uq_agent_version"),)

    id: Mapped[uuid.UUID] = mapped_column(GUID, primary_key=True, default=_uuid)
    agent_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("agents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    changelog: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        GUID, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    agent: Mapped[Agent] = relationship(back_populates="versions")


class AgentRun(Base, TimestampMixin):
    __tablename__ = "agent_runs"
    __table_args__ = (
        Index("ix_agent_runs_agent_created", "agent_id", "created_at"),
        Index("ix_agent_runs_status_created", "status", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(GUID, primary_key=True, default=_uuid)
    agent_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("agents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    agent_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    correlation_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="running", index=True)
    input_text: Mapped[str] = mapped_column(Text, nullable=False)
    output_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    model_name: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    used_fallback: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    estimated_cost: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(60), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    guardrail_outcome: Mapped[str] = mapped_column(String(20), nullable=False, default="pass")
    evaluation_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    citations: Mapped[list[dict]] = mapped_column(JSON, default=list, nullable=False)
    trace: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    agent: Mapped[Agent] = relationship(back_populates="runs")
    steps: Mapped[list[AgentRunStep]] = relationship(
        back_populates="run", cascade="all, delete-orphan", order_by="AgentRunStep.step_index"
    )


class AgentRunStep(Base):
    __tablename__ = "agent_run_steps"

    id: Mapped[uuid.UUID] = mapped_column(GUID, primary_key=True, default=_uuid)
    run_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    step_index: Mapped[int] = mapped_column(Integer, nullable=False)
    node: Mapped[str] = mapped_column(String(60), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ok")
    started_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    detail: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    run: Mapped[AgentRun] = relationship(back_populates="steps")


# --------------------------------------------------------------------------- rag


class RagPipeline(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "rag_pipelines"

    id: Mapped[uuid.UUID] = mapped_column(GUID, primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(200), nullable=False, unique=True, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    chunk_size: Mapped[int] = mapped_column(Integer, nullable=False, default=900)
    chunk_overlap: Mapped[int] = mapped_column(Integer, nullable=False, default=150)
    embedding_model: Mapped[str] = mapped_column(
        String(120), nullable=False, default="local-hash-embedding"
    )
    top_k: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    similarity_threshold: Mapped[float] = mapped_column(Float, nullable=False, default=0.05)
    reranking_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    metadata_filters: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    __table_args__ = (
        CheckConstraint("chunk_size > chunk_overlap", name="ck_chunk_overlap_lt_size"),
        CheckConstraint("top_k > 0", name="ck_top_k_positive"),
    )


class Document(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(GUID, primary_key=True, default=_uuid)
    filename: Mapped[str] = mapped_column(String(400), nullable=False, index=True)
    content_type: Mapped[str] = mapped_column(String(120), nullable=False, default="text/plain")
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    storage_uri: Mapped[str | None] = mapped_column(String(600), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending", index=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    extracted_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    page_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    doc_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    pipeline_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID, ForeignKey("rag_pipelines.id", ondelete="SET NULL"), nullable=True, index=True
    )
    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(
        GUID, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    indexed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    chunks: Mapped[list[DocumentChunk]] = relationship(
        back_populates="document", cascade="all, delete-orphan", order_by="DocumentChunk.ordinal"
    )


class DocumentChunk(Base):
    __tablename__ = "document_chunks"
    __table_args__ = (
        UniqueConstraint("document_id", "ordinal", name="uq_chunk_document_ordinal"),
    )

    id: Mapped[uuid.UUID] = mapped_column(GUID, primary_key=True, default=_uuid)
    document_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    token_estimate: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    embedding: Mapped[list[float] | None] = mapped_column(JSON, nullable=True)
    embedding_model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    chunk_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)

    document: Mapped[Document] = relationship(back_populates="chunks")


# --------------------------------------------------------------------------- governance


class GuardrailPolicy(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "guardrail_policies"

    id: Mapped[uuid.UUID] = mapped_column(GUID, primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(200), nullable=False, unique=True, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    detect_prompt_injection: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    redact_pii: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    block_on_injection: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    max_input_chars: Mapped[int] = mapped_column(Integer, default=8000, nullable=False)
    banned_phrases: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    tool_allowlist: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    domain_allowlist: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    require_citations: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class GuardrailEvent(Base):
    __tablename__ = "guardrail_events"

    id: Mapped[uuid.UUID] = mapped_column(GUID, primary_key=True, default=_uuid)
    run_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID, ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=True, index=True
    )
    policy_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID, ForeignKey("guardrail_policies.id", ondelete="SET NULL"), nullable=True
    )
    stage: Mapped[str] = mapped_column(String(20), nullable=False)  # input|output
    rule: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(20), nullable=False, default="low")
    action: Mapped[str] = mapped_column(String(20), nullable=False, default="flagged")
    detail: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, default=utcnow, nullable=False, index=True
    )


class UsageRecord(Base):
    """One row per billable model call. Cost is stored, never recomputed on read."""

    __tablename__ = "usage_records"
    __table_args__ = (Index("ix_usage_occurred_model", "occurred_at", "model_name"),)

    id: Mapped[uuid.UUID] = mapped_column(GUID, primary_key=True, default=_uuid)
    run_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID, ForeignKey("agent_runs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    agent_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID, ForeignKey("agents.id", ondelete="SET NULL"), nullable=True, index=True
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    model_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID, ForeignKey("models.id", ondelete="SET NULL"), nullable=True
    )
    model_name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    team: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    operation: Mapped[str] = mapped_column(String(40), nullable=False, default="chat")
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    estimated_cost: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    succeeded: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        UTCDateTime, default=utcnow, nullable=False, index=True
    )
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class Budget(Base, TimestampMixin):
    __tablename__ = "budgets"

    id: Mapped[uuid.UUID] = mapped_column(GUID, primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    scope: Mapped[str] = mapped_column(String(20), nullable=False, default="monthly")
    amount: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    warning_threshold: Mapped[float] = mapped_column(Float, nullable=False, default=0.8)
    team: Mapped[str | None] = mapped_column(String(100), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


# --------------------------------------------------------------------------- evaluation


class EvaluationDataset(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "evaluation_datasets"

    id: Mapped[uuid.UUID] = mapped_column(GUID, primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(200), nullable=False, unique=True, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    items: Mapped[list[dict]] = mapped_column(JSON, default=list, nullable=False)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class EvaluationRun(Base, TimestampMixin):
    __tablename__ = "evaluation_runs"

    id: Mapped[uuid.UUID] = mapped_column(GUID, primary_key=True, default=_uuid)
    dataset_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("evaluation_datasets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    agent_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID, ForeignKey("agents.id", ondelete="SET NULL"), nullable=True, index=True
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending", index=True)
    pass_threshold: Mapped[float] = mapped_column(Float, nullable=False, default=0.7)
    aggregate_scores: Mapped[dict[str, float]] = mapped_column(JSON, default=dict, nullable=False)
    passed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    regression_detected: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    triggered_by: Mapped[uuid.UUID | None] = mapped_column(
        GUID, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    results: Mapped[list[EvaluationResult]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )


class EvaluationResult(Base):
    __tablename__ = "evaluation_results"

    id: Mapped[uuid.UUID] = mapped_column(GUID, primary_key=True, default=_uuid)
    run_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("evaluation_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    item_index: Mapped[int] = mapped_column(Integer, nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    expected: Mapped[str | None] = mapped_column(Text, nullable=True)
    answer: Mapped[str] = mapped_column(Text, nullable=False, default="")
    scores: Mapped[dict[str, float]] = mapped_column(JSON, default=dict, nullable=False)
    passed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)

    run: Mapped[EvaluationRun] = relationship(back_populates="results")


# --------------------------------------------------------------------------- operations


class AzureResource(Base, TimestampMixin):
    __tablename__ = "azure_resources"

    id: Mapped[uuid.UUID] = mapped_column(GUID, primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    resource_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    region: Mapped[str] = mapped_column(String(60), nullable=False, default="eastus")
    resource_group: Mapped[str | None] = mapped_column(String(120), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="unknown", index=True)
    # "live" when read from Azure Monitor, "mock" when produced by the local collector.
    data_source: Mapped[str] = mapped_column(String(10), nullable=False, default="mock")
    availability_pct: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    latency_p95_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_rate_pct: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    throughput_rpm: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    quota_used_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_checked_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class HealthMetric(Base):
    __tablename__ = "health_metrics"
    __table_args__ = (Index("ix_health_component_recorded", "component", "recorded_at"),)

    id: Mapped[uuid.UUID] = mapped_column(GUID, primary_key=True, default=_uuid)
    component: Mapped[str] = mapped_column(String(60), nullable=False)
    metric: Mapped[str] = mapped_column(String(60), nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str] = mapped_column(String(20), nullable=False, default="ms")
    recorded_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)


class Alert(Base, TimestampMixin):
    __tablename__ = "alerts"

    id: Mapped[uuid.UUID] = mapped_column(GUID, primary_key=True, default=_uuid)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    severity: Mapped[str] = mapped_column(String(20), nullable=False, default="info", index=True)
    source: Mapped[str] = mapped_column(String(60), nullable=False, default="platform")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active", index=True)
    acknowledged_by: Mapped[uuid.UUID | None] = mapped_column(
        GUID, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    acknowledged_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    context: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (Index("ix_audit_created_action", "created_at", "action"),)

    id: Mapped[uuid.UUID] = mapped_column(GUID, primary_key=True, default=_uuid)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    actor_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    action: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    resource_type: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    resource_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    outcome: Mapped[str] = mapped_column(String(20), nullable=False, default="success")
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Written through app.core.logging.redact — never store raw secrets here.
    changes: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, default=utcnow, nullable=False, index=True
    )
