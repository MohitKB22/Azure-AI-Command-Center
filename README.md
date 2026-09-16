# Azure AI Command Center

An enterprise control plane for operating AI agents: register and version agents,
run them as inspectable graphs, ingest and index documents, manage prompts and
models, evaluate quality, enforce guardrails, and track tokens, cost and service
health.

It runs **completely offline** with deterministic in-process providers, and
switches to Azure OpenAI, Azure AI Search, Blob Storage and Azure Monitor by
changing environment variables — no code changes.

> **Status.** This is a working vertical slice, not a finished product. Read
> [BUILD_REPORT.md](BUILD_REPORT.md) for exactly what was verified, what was
> verified with mocks, and what still requires an Azure subscription. Nothing in
> this repository has been deployed to Azure.

---

## Quick start

Requires Python 3.11+ (3.12 recommended) and Node 20+.

```bash
git clone <your-fork-url> azure-ai-command-center
cd azure-ai-command-center

./scripts/dev.sh setup     # venv, deps, .env, migrations, demo seed data

# then, in two terminals:
./scripts/dev.sh api       # http://localhost:8000/docs
./scripts/dev.sh web       # http://localhost:5173
```

Sign in with **admin@contoso.com / Passw0rd!Demo**. Four other seeded accounts
(`engineer@`, `dev@`, `analyst@`, `viewer@contoso.com`) use the same password and
demonstrate role-based access control.

### With Docker

```bash
cp .env.example .env
make up          # postgres, redis, qdrant, migrations, api, worker, web + seed
make down        # tear down and remove volumes
```

---

## What actually works

Every item below is exercised by the automated test suite:

| Capability | Detail |
|---|---|
| Agent lifecycle | Create, edit, duplicate, enable/disable, version, roll back, archive |
| Agent execution | Nine-node LangGraph pipeline with retries, model fallback and full traces |
| RAG ingestion | PDF / DOCX / TXT / MD / CSV / JSON → extract → chunk → embed → index |
| Retrieval | Cosine search, similarity threshold, hybrid reranking, citations |
| Guardrails | Prompt-injection detection, PII redaction, tool allowlists, citation enforcement |
| Prompts | Registry, versioning, variables, rendering, promotion, rollback |
| Models | Catalogue with per-model cost configuration and routing defaults |
| Evaluation | Eight metrics, datasets, pass thresholds, regression detection, CSV export |
| Cost | Per-request attribution by model, agent and team, with budgets |
| Monitoring | Component health checks and an Azure resource inventory |
| Audit | Append-only log of every mutation, with secret redaction |
| Security | JWT + API keys, RBAC, rate limiting, upload validation, security headers |

## What is deliberately honest about its limits

- **Local mode does not hallucinate.** The offline LLM is *extractive*: it
  answers only with sentences drawn from retrieved context, and says so when the
  context does not cover the question. It never invents a citation.
- **Azure metrics are never faked.** A resource with no credentials reports
  `not_configured` and zeroes. Nothing synthesises a plausible-looking uptime.
- **Guardrails are heuristics, not a security boundary.** The UI says so, the API
  says so in `/api/v1/guardrails/rules`, and the source says so at the top of
  `app/services/guardrails.py`.
- **Evaluation scores are lexical proxies**, reproducible without a judge model.
  Swap in an LLM judge for production-grade semantic scoring.

---

## Architecture at a glance

```
apps/web (React 18 + TS + Vite + Tailwind + TanStack Query)
    │  REST /api/v1
apps/api (FastAPI + Pydantic v2 + SQLAlchemy 2 + Alembic)
    ├── api/routes/     14 routers, versioned, RBAC on every endpoint
    ├── services/       agent graph, RAG, guardrails, evaluation, cost, audit
    ├── providers/      LLM · embeddings · vector store · blob  (local | azure)
    └── db/             24 tables, UUID keys, soft delete, seed data
        │
        ├── PostgreSQL (SQLite locally)
        ├── Qdrant (in-database exact search locally)
        └── Blob Storage (local filesystem locally)
```

Full detail in [ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Provider modes

| Variable | `local` (default) | `azure` |
|---|---|---|
| `LLM_PROVIDER` | Deterministic extractive responder | Azure OpenAI chat completions |
| `EMBEDDING_PROVIDER` | Hashed bag-of-words, 768-dim | Azure OpenAI embeddings |
| `VECTOR_STORE` | Exact cosine search in PostgreSQL/SQLite | Qdrant |
| `BLOB_PROVIDER` | Local filesystem | Azure Blob Storage + Managed Identity |

The active mode is reported at `/health/ready`, on the Overview page, and on
every run trace.

## Documentation

| Document | Contents |
|---|---|
| [ARCHITECTURE.md](docs/ARCHITECTURE.md) | Components, request flow, RAG flow, agent graph, ER diagram |
| [API.md](docs/API.md) | Every endpoint, auth, pagination, error format |
| [SECURITY.md](docs/SECURITY.md) | Threat model, controls, what is and is not covered |
| [DEVELOPMENT.md](docs/DEVELOPMENT.md) | Local workflow, conventions, adding features |
| [TESTING.md](docs/TESTING.md) | Test layers and how to run each |
| [DEPLOYMENT.md](docs/DEPLOYMENT.md) | Environments, CI/CD, rollback |
| [AZURE.md](docs/AZURE.md) | Azure resources, identity, switching to live services |
| [TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) | Common failures and fixes |
| [CONTRIBUTING.md](docs/CONTRIBUTING.md) | Standards and review expectations |
| [BUILD_REPORT.md](BUILD_REPORT.md) | Verified / mocked / not verified, honestly |

## Commands

```bash
make setup     # install everything, migrate, seed
make api       # run the API
make web       # run the UI
make test      # backend + frontend tests
make check     # the full CI gate locally
make up        # docker compose stack
```

## Licence

Provided as-is for evaluation. Add a licence before distributing.
