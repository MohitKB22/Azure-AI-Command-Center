# Architecture

## Guiding decisions

| Decision | Rationale |
|---|---|
| Modular monolith, not microservices | One team, one deploy unit, one transaction boundary. Module seams are enforced by package structure so a service can be extracted later if load justifies it. |
| Synchronous SQLAlchemy | The workload is request/response with short queries. Async SQLAlchemy adds session-lifecycle complexity and a second set of driver bugs for no measurable gain at this scale. |
| Provider interfaces for every external dependency | The whole platform runs and is tested offline. Switching to Azure is configuration, not a rewrite. |
| Acyclic agent graph | An agent that cannot loop cannot burn budget in a loop. Retries and fallback are bounded counters inside one node. |
| Cost stored at write time | Repricing a model must not silently rewrite last quarter's spend. |
| Soft delete on user-facing entities | Auditors need the history; users need the entity gone from their list. |

## Component map

```
┌──────────────────────────────────────────────────────────────────┐
│  apps/web — React 18, TypeScript, Vite, Tailwind                 │
│  TanStack Query (server state) · Zustand (session) · Recharts    │
└───────────────────────────┬──────────────────────────────────────┘
                            │ REST /api/v1 · Bearer JWT or X-API-Key
┌───────────────────────────▼──────────────────────────────────────┐
│  apps/api — FastAPI                                              │
│                                                                  │
│  middleware   request ID · correlation ID · rate limit · headers │
│  api/routes   auth users agents runs models prompts documents    │
│               rag guardrails evaluations monitoring costs audit  │
│  services     agent_graph runner rag chunking guardrails         │
│               evaluation costs monitoring audit tools            │
│  providers    llm · embeddings · vector_store · blob · azure_auth│
│  core         config db security rbac deps errors logging        │
│  db           models (24 tables) · seed                          │
└───────┬───────────────┬──────────────┬───────────────┬───────────┘
        │               │              │               │
   PostgreSQL       Qdrant        Blob Storage    Azure OpenAI
   (SQLite local)  (SQL local)   (filesystem)     (local LLM)
```

`workers/` runs the same codebase (`app.worker`) on a timer for metric
collection, alert evaluation and ingestion retries.

## Request flow

```
Browser
  │ 1. fetch with Bearer token
  ▼
RequestContextMiddleware   assigns request_id, propagates correlation_id
  │
RateLimitMiddleware        fixed window per key/JWT/IP
  │
MaxBodySizeMiddleware      rejects oversized bodies before buffering
  │
CORS                       explicit origin allowlist
  │
Route dependency           get_current_user → require_permission("x:write")
  │
Service layer              business rules, raises typed AppError subclasses
  │
Repository / ORM           SQLAlchemy session scoped to the request
  │
audit.record()             every mutation, with secrets redacted
  │
Response                   Pydantic schema, or the standard error envelope
```

Every response carries `X-Request-ID` and `X-Correlation-ID`. Every log line
carries both. That pairing is what makes an incident traceable from a browser
network tab to a specific agent run and its retrieval decisions.

## Agent execution graph

Built with LangGraph. Nodes are pure functions over a typed state dict; the
graph is acyclic, so termination is structural rather than a guard.

```
START
  ▼
validate_input      reject empty input
  ▼
guardrail_input     injection detection → block | redact | allow
  ▼
route               tool · retrieval · direct
  ▼
retrieve            RAG pipeline → chunks + citations
  ▼
tools               allowlisted tools only; failures are recorded, not fatal
  ▼
assemble_context    numbered blocks, character budget
  ▼
generate            primary model → retries → fallback model
  ▼
guardrail_output    PII redaction, citation requirement, banned phrases
  ▼
telemetry           final status
  ▼
END
```

Each node appends a step record with duration and detail. The run inspector
renders these directly, which is what makes "was this slow in retrieval or in
generation?" answerable in one glance.

**Failure semantics**

| Failure | Behaviour |
|---|---|
| Empty input | `failed`, no model call |
| High-severity injection | `blocked`, no model call, guardrail event written |
| Primary model error | Retry up to `max_retries`, then fallback model, flagged `used_fallback` |
| Both models fail | `failed` with `generation_failed`, no partial output |
| Tool error | Recorded in the trace; generation continues without that tool |
| Output violates policy | `blocked`, generated text withheld |

## RAG flow

```
Upload ─▶ validate (extension, size, traversal, checksum dedupe)
      ─▶ store raw bytes (filesystem | Blob Storage)
      ─▶ extract   PDF (pypdf, page markers) · DOCX (zip+XML) · CSV · JSON · text
      ─▶ normalise NFKC, whitespace, newline collapsing
      ─▶ chunk     sentence-aware sliding window, overlap, page tracking
      ─▶ embed     hashed bag-of-words (local) | Azure OpenAI
      ─▶ index     SQL exact cosine | Qdrant
Query ─▶ embed query
      ─▶ search    over-fetch 4×K candidates
      ─▶ threshold drop everything below similarity_threshold
      ─▶ rerank    0.65 × vector + 0.35 × lexical overlap
      ─▶ assemble  numbered blocks within a character budget
      ─▶ generate  grounded answer
      ─▶ cite      document name, page, score, snippet
```

Ingestion is idempotent: reprocessing deletes and rebuilds a document's chunks
rather than appending. A failure marks the document `failed` with the reason
instead of leaving it stuck in `processing`.

## Data model

24 tables. UUID primary keys, timezone-aware timestamps, foreign keys with
explicit `ondelete`, indexes on every FK and every filtered column.

```
users ──┬──< api_keys
        ├──< agents ──┬──< agent_versions
        │             ├──< agent_runs ──┬──< agent_run_steps
        │             │                 ├──< guardrail_events
        │             │                 └──< usage_records
        │             └──> models
        │             └──> rag_pipelines
        │             └──> guardrail_policies
        ├──< prompts ──< prompt_versions
        ├──< documents ──< document_chunks
        ├──< evaluation_datasets ──< evaluation_runs ──< evaluation_results
        └──< audit_logs

standalone: azure_resources · health_metrics · alerts · budgets
```

Notable columns:

- `document_chunks.embedding` — JSON float array; the local vector store scores
  these in-process. Qdrant mode keeps the same rows and mirrors vectors out.
- `agent_runs.trace` — providers, routing, retrieval config, attempt count.
- `usage_records.estimated_cost` — computed once, at write time.
- `azure_resources.data_source` — `local` | `live` | `none`; `none` guarantees no
  metric was invented.

## Deployment shape

```
                    ┌────────────────────┐
  Users ── HTTPS ──▶│ Container App: web │ (nginx, static bundle)
                    └─────────┬──────────┘
                              │ /api/v1
                    ┌─────────▼──────────┐
                    │ Container App: api │◀── Managed Identity
                    └─┬────────┬─────────┘
                      │        │
        ┌─────────────┘        └──────────────┐
        ▼                                     ▼
  PostgreSQL Flexible Server          Azure OpenAI · AI Search
  (Entra auth, private access)        Blob Storage · Key Vault
                      │
              ┌───────▼────────┐
              │ Container App  │  worker: metrics, alerts, retries
              │      Job       │  migrations run as a one-off job
              └────────────────┘
                      │
              Application Insights ─▶ Log Analytics
```

No component holds a long-lived credential: PostgreSQL uses Entra
authentication, Storage disables shared-key access, and Azure OpenAI has
`disableLocalAuth: true`. The API's user-assigned identity holds one narrowly
scoped role per resource.
