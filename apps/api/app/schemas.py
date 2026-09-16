"""Pydantic v2 request/response contracts for the public API."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.core.rbac import Role


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --------------------------------------------------------------------- auth


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=200)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: datetime
    user: UserOut


class UserOut(ORMModel):
    id: uuid.UUID
    email: EmailStr
    full_name: str
    role: Role
    team: str | None = None
    is_active: bool
    is_demo: bool
    last_login_at: datetime | None = None
    created_at: datetime


class UserCreate(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=8, max_length=200)
    role: Role = Role.VIEWER
    team: str | None = Field(default=None, max_length=100)


class UserUpdate(BaseModel):
    full_name: str | None = Field(default=None, max_length=200)
    role: Role | None = None
    team: str | None = Field(default=None, max_length=100)
    is_active: bool | None = None


class MeResponse(BaseModel):
    user: UserOut
    permissions: list[str]
    demo_mode: bool
    environment: str


class ApiKeyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    expires_in_days: int | None = Field(default=None, ge=1, le=730)


class ApiKeyOut(ORMModel):
    id: uuid.UUID
    name: str
    key_prefix: str
    created_at: datetime
    expires_at: datetime | None
    revoked_at: datetime | None
    last_used_at: datetime | None


class ApiKeyCreated(BaseModel):
    api_key: ApiKeyOut
    # Returned once, never stored in plaintext.
    key: str


# -------------------------------------------------------------------- models


class ModelOut(ORMModel):
    id: uuid.UUID
    name: str
    provider: str
    deployment_name: str
    kind: str
    context_window: int
    max_output_tokens: int
    capabilities: list[str]
    input_cost_per_1k: float
    output_cost_per_1k: float
    currency: str
    status: str
    is_default: bool
    is_fallback: bool
    is_demo: bool
    notes: str | None = None
    created_at: datetime


class ModelCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    provider: str = Field(default="azure_openai", max_length=60)
    deployment_name: str = Field(min_length=1, max_length=120)
    kind: str = Field(default="chat", pattern="^(chat|embedding)$")
    context_window: int = Field(default=8192, gt=0, le=2_000_000)
    max_output_tokens: int = Field(default=4096, gt=0, le=200_000)
    capabilities: list[str] = Field(default_factory=list)
    input_cost_per_1k: float = Field(default=0.0, ge=0)
    output_cost_per_1k: float = Field(default=0.0, ge=0)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    status: str = Field(default="available", max_length=20)
    is_default: bool = False
    is_fallback: bool = False
    notes: str | None = None


class ModelUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=120)
    context_window: int | None = Field(default=None, gt=0)
    max_output_tokens: int | None = Field(default=None, gt=0)
    capabilities: list[str] | None = None
    input_cost_per_1k: float | None = Field(default=None, ge=0)
    output_cost_per_1k: float | None = Field(default=None, ge=0)
    status: str | None = Field(default=None, max_length=20)
    is_default: bool | None = None
    is_fallback: bool | None = None
    notes: str | None = None


# -------------------------------------------------------------------- agents


class AgentSummary(ORMModel):
    id: uuid.UUID
    name: str
    slug: str
    description: str | None
    status: str
    environment: str
    enabled: bool
    rag_enabled: bool
    tools: list[str]
    tags: list[str]
    current_version: int
    model_id: uuid.UUID | None
    is_demo: bool
    created_at: datetime
    updated_at: datetime


class AgentDetail(AgentSummary):
    system_prompt: str
    temperature: float
    max_output_tokens: int
    timeout_seconds: int
    max_retries: int
    memory_enabled: bool
    fallback_model_id: uuid.UUID | None
    rag_pipeline_id: uuid.UUID | None
    guardrail_policy_id: uuid.UUID | None
    model: ModelOut | None = None


class AgentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    system_prompt: str = Field(default="", max_length=20_000)
    model_id: uuid.UUID | None = None
    fallback_model_id: uuid.UUID | None = None
    temperature: float = Field(default=0.2, ge=0, le=2)
    max_output_tokens: int = Field(default=800, gt=0, le=32_000)
    timeout_seconds: int = Field(default=60, gt=0, le=600)
    max_retries: int = Field(default=1, ge=0, le=5)
    tools: list[str] = Field(default_factory=list)
    memory_enabled: bool = False
    rag_enabled: bool = True
    rag_pipeline_id: uuid.UUID | None = None
    guardrail_policy_id: uuid.UUID | None = None
    environment: str = Field(default="development", pattern="^(development|staging|production)$")
    status: str = Field(default="draft", pattern="^(draft|active|paused|archived)$")
    enabled: bool = True
    tags: list[str] = Field(default_factory=list)

    @field_validator("tags", "tools")
    @classmethod
    def _dedupe(cls, value: list[str]) -> list[str]:
        return sorted({item.strip() for item in value if item.strip()})


class AgentUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    system_prompt: str | None = Field(default=None, max_length=20_000)
    model_id: uuid.UUID | None = None
    fallback_model_id: uuid.UUID | None = None
    temperature: float | None = Field(default=None, ge=0, le=2)
    max_output_tokens: int | None = Field(default=None, gt=0, le=32_000)
    timeout_seconds: int | None = Field(default=None, gt=0, le=600)
    max_retries: int | None = Field(default=None, ge=0, le=5)
    tools: list[str] | None = None
    memory_enabled: bool | None = None
    rag_enabled: bool | None = None
    rag_pipeline_id: uuid.UUID | None = None
    guardrail_policy_id: uuid.UUID | None = None
    environment: str | None = Field(default=None, pattern="^(development|staging|production)$")
    status: str | None = Field(default=None, pattern="^(draft|active|paused|archived)$")
    enabled: bool | None = None
    tags: list[str] | None = None


class AgentVersionOut(ORMModel):
    id: uuid.UUID
    version: int
    changelog: str | None
    snapshot: dict[str, Any]
    created_at: datetime


class AgentRunRequest(BaseModel):
    input: str = Field(min_length=1, max_length=20_000)
    correlation_id: str | None = Field(default=None, max_length=64)


# ---------------------------------------------------------------------- runs


class RunStepOut(ORMModel):
    step_index: int
    node: str
    status: str
    duration_ms: int
    detail: dict[str, Any]


class RunSummary(ORMModel):
    id: uuid.UUID
    agent_id: uuid.UUID
    agent_version: int
    status: str
    model_name: str | None
    used_fallback: bool
    total_tokens: int
    estimated_cost: float
    latency_ms: int
    guardrail_outcome: str
    evaluation_score: float | None
    created_at: datetime


class RunDetail(RunSummary):
    input_text: str
    output_text: str | None
    prompt_tokens: int
    completion_tokens: int
    error_code: str | None
    error_message: str | None
    correlation_id: str | None
    citations: list[dict[str, Any]]
    trace: dict[str, Any]
    steps: list[RunStepOut] = Field(default_factory=list)


# ----------------------------------------------------------------- documents


class DocumentOut(ORMModel):
    id: uuid.UUID
    filename: str
    content_type: str
    size_bytes: int
    status: str
    error_message: str | None
    page_count: int
    chunk_count: int
    version: int
    tags: list[str]
    pipeline_id: uuid.UUID | None
    indexed_at: datetime | None
    is_demo: bool
    created_at: datetime


class DocumentDetail(DocumentOut):
    extracted_text_preview: str | None = None
    doc_metadata: dict[str, Any] = Field(default_factory=dict)
    storage_uri: str | None = None


class ChunkOut(ORMModel):
    id: uuid.UUID
    ordinal: int
    content: str
    token_estimate: int
    page: int | None
    embedding_model: str | None


# ----------------------------------------------------------------------- rag


class PipelineOut(ORMModel):
    id: uuid.UUID
    name: str
    description: str | None
    chunk_size: int
    chunk_overlap: int
    embedding_model: str
    top_k: int
    similarity_threshold: float
    reranking_enabled: bool
    metadata_filters: dict[str, Any]
    is_default: bool
    is_demo: bool
    created_at: datetime


class PipelineCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=1000)
    chunk_size: int = Field(default=900, ge=100, le=8000)
    chunk_overlap: int = Field(default=150, ge=0, le=2000)
    top_k: int = Field(default=5, ge=1, le=50)
    similarity_threshold: float = Field(default=0.05, ge=0, le=1)
    reranking_enabled: bool = True
    metadata_filters: dict[str, Any] = Field(default_factory=dict)
    is_default: bool = False

    @field_validator("chunk_overlap")
    @classmethod
    def _overlap_below_size(cls, value: int, info) -> int:
        size = info.data.get("chunk_size", 900)
        if value >= size:
            raise ValueError("chunk_overlap must be smaller than chunk_size")
        return value


class PipelineUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    description: str | None = None
    chunk_size: int | None = Field(default=None, ge=100, le=8000)
    chunk_overlap: int | None = Field(default=None, ge=0, le=2000)
    top_k: int | None = Field(default=None, ge=1, le=50)
    similarity_threshold: float | None = Field(default=None, ge=0, le=1)
    reranking_enabled: bool | None = None
    metadata_filters: dict[str, Any] | None = None
    is_default: bool | None = None


class RagQueryRequest(BaseModel):
    query: str = Field(min_length=1, max_length=4000)
    pipeline_id: uuid.UUID | None = None
    top_k: int | None = Field(default=None, ge=1, le=50)
    similarity_threshold: float | None = Field(default=None, ge=0, le=1)
    use_reranking: bool | None = None
    document_ids: list[uuid.UUID] | None = None
    generate_answer: bool = True
    agent_id: uuid.UUID | None = None


class RetrievedChunkOut(BaseModel):
    chunk_id: str
    document_id: str
    document_name: str
    ordinal: int
    page: int | None
    content: str
    score: float
    rerank_score: float | None = None


class RagQueryResponse(BaseModel):
    query: str
    answer: str | None
    citations: list[dict[str, Any]]
    chunks: list[RetrievedChunkOut]
    candidates_considered: int
    latency_ms: int
    pipeline: dict[str, Any]
    stages: list[dict[str, Any]]
    run_id: uuid.UUID | None = None


# --------------------------------------------------------------- guardrails


class GuardrailPolicyOut(ORMModel):
    id: uuid.UUID
    name: str
    description: str | None
    detect_prompt_injection: bool
    redact_pii: bool
    block_on_injection: bool
    max_input_chars: int
    banned_phrases: list[str]
    tool_allowlist: list[str]
    domain_allowlist: list[str]
    require_citations: bool
    is_default: bool
    created_at: datetime


class GuardrailPolicyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    detect_prompt_injection: bool = True
    redact_pii: bool = True
    block_on_injection: bool = True
    max_input_chars: int = Field(default=8000, ge=100, le=200_000)
    banned_phrases: list[str] = Field(default_factory=list)
    tool_allowlist: list[str] = Field(default_factory=list)
    domain_allowlist: list[str] = Field(default_factory=list)
    require_citations: bool = False
    is_default: bool = False


class GuardrailTestRequest(BaseModel):
    text: str = Field(min_length=1, max_length=20_000)
    stage: str = Field(default="input", pattern="^(input|output)$")
    policy_id: uuid.UUID | None = None


class GuardrailFindingOut(BaseModel):
    rule: str
    severity: str
    detail: dict[str, Any]


class GuardrailTestResponse(BaseModel):
    action: str
    outcome: str
    text: str
    findings: list[GuardrailFindingOut]


class GuardrailEventOut(ORMModel):
    id: uuid.UUID
    run_id: uuid.UUID | None
    stage: str
    rule: str
    severity: str
    action: str
    detail: dict[str, Any]
    created_at: datetime


# --------------------------------------------------------------- evaluations


class DatasetOut(ORMModel):
    id: uuid.UUID
    name: str
    description: str | None
    items: list[dict[str, Any]]
    is_demo: bool
    created_at: datetime


class DatasetCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    items: list[dict[str, Any]] = Field(default_factory=list)


class EvaluationRunRequest(BaseModel):
    dataset_id: uuid.UUID
    agent_id: uuid.UUID
    pass_threshold: float = Field(default=0.5, ge=0, le=1)


class EvaluationResultOut(ORMModel):
    item_index: int
    question: str
    expected: str | None
    answer: str
    scores: dict[str, float]
    passed: bool
    latency_ms: int
    total_tokens: int


class EvaluationRunOut(ORMModel):
    id: uuid.UUID
    dataset_id: uuid.UUID
    agent_id: uuid.UUID | None
    status: str
    pass_threshold: float
    aggregate_scores: dict[str, float]
    passed: bool | None
    regression_detected: bool
    duration_ms: int
    created_at: datetime


class EvaluationRunDetail(EvaluationRunOut):
    results: list[EvaluationResultOut] = Field(default_factory=list)


# -------------------------------------------------------------------- prompts


class PromptVersionOut(ORMModel):
    id: uuid.UUID
    version: int
    template: str
    variables: list[str]
    environment: str
    approval_status: str
    changelog: str | None
    created_at: datetime


class PromptOut(ORMModel):
    id: uuid.UUID
    key: str
    name: str
    description: str | None
    tags: list[str]
    active_version: int
    is_demo: bool
    created_at: datetime
    updated_at: datetime


class PromptDetail(PromptOut):
    versions: list[PromptVersionOut] = Field(default_factory=list)


class PromptCreate(BaseModel):
    key: str = Field(min_length=1, max_length=120, pattern=r"^[a-z0-9][a-z0-9._-]*$")
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    template: str = Field(min_length=1, max_length=20_000)
    tags: list[str] = Field(default_factory=list)


class PromptVersionCreate(BaseModel):
    template: str = Field(min_length=1, max_length=20_000)
    changelog: str | None = Field(default=None, max_length=1000)
    environment: str = Field(default="development", pattern="^(development|staging|production)$")
    approval_status: str = Field(default="draft", pattern="^(draft|approved|rejected)$")


class PromptRenderRequest(BaseModel):
    variables: dict[str, str] = Field(default_factory=dict)
    version: int | None = None


class PromptRenderResponse(BaseModel):
    rendered: str
    missing_variables: list[str]
    version: int


# ------------------------------------------------------------------ ops/cost


class AzureResourceOut(ORMModel):
    id: uuid.UUID
    name: str
    resource_type: str
    region: str
    resource_group: str | None
    status: str
    data_source: str
    availability_pct: float
    latency_p95_ms: int
    error_rate_pct: float
    throughput_rpm: float
    quota_used_pct: float | None
    last_checked_at: datetime | None
    details: dict[str, Any]
    is_demo: bool


class AlertOut(ORMModel):
    id: uuid.UUID
    title: str
    description: str | None
    severity: str
    source: str
    status: str
    acknowledged_at: datetime | None
    resolved_at: datetime | None
    context: dict[str, Any]
    created_at: datetime


class AuditLogOut(ORMModel):
    id: uuid.UUID
    actor_email: str | None
    action: str
    resource_type: str
    resource_id: str | None
    outcome: str
    request_id: str | None
    changes: dict[str, Any]
    created_at: datetime


class OverviewResponse(BaseModel):
    generated_at: datetime
    demo_mode: bool
    environment: str
    providers: dict[str, str]
    kpis: dict[str, Any]
    timeseries: list[dict[str, Any]]
    model_usage: list[dict[str, Any]]
    agent_activity: list[dict[str, Any]]
    recent_runs: list[RunSummary]
    active_alerts: list[AlertOut]
    health: dict[str, Any]


class CostSummaryResponse(BaseModel):
    totals: dict[str, Any]
    timeseries: list[dict[str, Any]]
    by_model: list[dict[str, Any]]
    by_agent: list[dict[str, Any]]
    by_team: list[dict[str, Any]]
    budgets: list[dict[str, Any]]


TokenResponse.model_rebuild()
