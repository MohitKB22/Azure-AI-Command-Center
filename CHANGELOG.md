# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] — 2026-08-16

First working vertical slice. See [BUILD_REPORT.md](BUILD_REPORT.md) for what was
verified and what was not.

### Added

**Platform**

- FastAPI control plane with 14 routers and 57 OpenAPI paths under `/api/v1`
- 24-table PostgreSQL schema with UUID keys, soft delete and a reversible
  Alembic baseline migration
- Provider abstraction for LLM, embeddings, vector store and blob storage, with
  deterministic local implementations and Azure implementations behind the same
  protocols
- JWT and API-key authentication; five-role RBAC enforced on every endpoint
- Structured JSON logging with request/correlation IDs and secret redaction
- Rate limiting, body size limits, security headers and CORS allowlisting

**AI**

- LangGraph agent execution: nine acyclic nodes with retries, bounded model
  fallback, tool failure tolerance and a persisted step-by-step trace
- RAG engine: extraction (PDF/DOCX/CSV/JSON/text), normalisation, sentence-aware
  chunking with page tracking, embedding, indexing, threshold filtering, hybrid
  reranking, context assembly and citations
- Guardrails with detection, policy and enforcement kept explicitly separate
- Evaluation with eight deterministic metrics, pass thresholds, regression
  detection and CSV export
- Closed tool registry: AST-based calculator, clock, URL policy check

**Operations**

- Cost tracking computed at write time from per-model configured rates, with
  budgets and threshold alerting
- Component health checks and an Azure resource inventory that reports
  `not_configured` rather than synthesising metrics
- Append-only audit log covering every mutation
- Background worker for metric collection, alert evaluation and ingestion retry

**Frontend**

- 17-route React command centre with a dark Azure-inspired design system
- Overview dashboard with seven charts and live system health
- Agent manager with inline versioning and a test runner
- Run inspector rendering the execution graph with per-node timings
- RAG playground with live pipeline visualisation and score breakdowns
- Document intelligence with drag-and-drop upload and chunk inspection
- Prompt registry with rendering, comparison and rollback
- Model centre, guardrail tester, evaluation dashboard, cost centre, alerts,
  audit log and settings

**Engineering**

- 102 backend tests and 24 frontend tests, all passing
- 11 Playwright E2E specs (written, not yet executed)
- CI, Docker and deploy GitHub Actions workflows
- Bicep infrastructure for three environments with Managed Identity and
  least-privilege role assignments
- Docker Compose stack and a one-command development script
- Eleven documents covering architecture, API, security, testing, deployment,
  Azure integration, troubleshooting and contribution standards

### Fixed during initial development

- FastAPI startup failure from combining `Annotated[..., Depends]` with a default
  `Depends` value in eight route modules
- 500 response on validation errors caused by a non-serialisable `ValueError` in
  the Pydantic error context
- Retrieval mis-ranking caused by signed hashed embeddings producing negative
  cosine scores for short queries
- Depressed groundedness scores caused by the local LLM appending boilerplate to
  answer text
- Alembic migration `NameError` from unrendered custom column type imports
- Frontend bundle exceeding the chunk size budget

### Known limitations

No OCR; synchronous ingestion and evaluation; per-process rate limiting; no
refresh-token rotation; no SSO or MFA; Azure AI Search provisioned but not wired
into retrieval; guardrails are heuristic rather than a security boundary.
