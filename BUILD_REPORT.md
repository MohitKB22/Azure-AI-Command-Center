# Build report

**Date:** 16 August 2026
**Version:** 0.1.0
**Scope:** Working vertical slice of the Azure AI Command Center.

This report exists because the build prompt asked for one, and because the
difference between "the code is written" and "the code was run" matters. Every
claim below is either something a command actually printed, or is listed as not
verified.

---

## 1. Verification status

### Verified locally — commands were run, output observed

| Check | Result |
|---|---|
| Alembic migration from an empty database | 24 tables created |
| `alembic downgrade base` then `upgrade head` | Both succeed; schema rebuilds cleanly |
| `alembic check` | "No new upgrade operations detected" — models match the migration |
| Seed script | 5 users, 6 models, 2 pipelines, 2 policies, 12 documents, 6 agents, 3 prompts, 8 real agent runs, 232 usage records |
| `ruff check .` | All checks passed |
| `pytest` | **102 passed**, 0 failed |
| API starts under uvicorn | `/health/ready` → `status: ready`, `database: up` |
| All 26 authenticated GET endpoints | Every one returned 200 |
| Error envelope | 401 `unauthenticated`, 422 `validation_error`, both with `request_id` |
| Security headers | `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, `X-Request-ID` present |
| Server log scan | 0 unhandled exceptions, 0 server-side 5xx |
| OpenAPI document | 57 paths, `/docs` renders |
| Frontend `tsc --noEmit` | No errors |
| Frontend `eslint --max-warnings 0` | Clean |
| Frontend `vitest` | **24 passed** |
| Frontend `vite build` | Succeeds; 4 chunks, largest 385 kB (107 kB gzipped) |

**Behaviour verified by the integration suite** (not just status codes):

- Agent lifecycle: create → edit (v2) → rollback (v3, original values restored) → archive → 404
- Agent execution produces exactly the nine expected graph nodes in order
- A grounded answer carries citations; a prompt injection is `blocked` before the model is called and records a guardrail event
- Document upload reaches `indexed`, is retrievable by content, and duplicate content is rejected with 409
- Asking "What caused incident 2043?" ranks the incident document first
- Raising `similarity_threshold` strictly reduces the result set
- RBAC: viewer cannot write agents or read users; engineer cannot create users
- A revoked API key stops authenticating immediately
- Evaluation scores every dataset item; the adversarial item scores `safety = 0.0`
- Unconfigured Azure resources report `not_configured` with zero metrics
- An issued API key never appears in the audit log

### Verified with deterministic local implementations

These are real, working code paths — not stubs — but they are the local
implementations, not Azure:

| Component | What it does | Limitation |
|---|---|---|
| `LocalGroundedLLM` | Extractive answering from retrieved context | Not generative. Cannot paraphrase or reason. Says so when context is insufficient. |
| `LocalHashEmbedding` | 768-dim hashed bag-of-words with bigrams | Lexical, not semantic. Synonyms do not match. |
| `SqlVectorStore` | Exact brute-force cosine over chunk embeddings | O(n) per query. Fine to ~100k chunks; use Qdrant beyond that. |
| `LocalBlobStore` | Filesystem storage with traversal protection | Single-node only. |
| `LocalMetricCollector` | Derives metrics from local usage records | Only reports what it can measure. Marks everything else `not_configured`. |
| Evaluation metrics | Deterministic lexical proxies | Not semantic entailment. Reproducible, but a judge model is better. |

### NOT verified — requires an Azure subscription

No Azure resource was provisioned. Nothing was deployed. The following is written
against documented API contracts and reviewed by inspection only:

- `AzureOpenAIChat` and `AzureOpenAIEmbedding` against a live endpoint
- Managed Identity token acquisition (`DefaultAzureCredential`)
- `AzureBlobStore` read/write
- `QdrantVectorStore` collection creation and search
- `AzureMonitorCollector` metric queries
- Bicep template deployment (`main.bicep`, three parameter files)
- All three GitHub Actions workflows
- PostgreSQL Entra authentication from Container Apps
- Docker image builds and `docker compose up` (Docker was unavailable in the build environment)
- Playwright E2E suite (11 specs are written but were not executed — no browser binaries available)

**Do not treat this as production-ready.** Deploy to `dev` first, run
`az deployment group what-if`, and work through the checklist in
`docs/SECURITY.md`.

---

## 2. What was built

### Backend — `apps/api`

FastAPI · Pydantic v2 · SQLAlchemy 2.0 · Alembic · LangGraph

```
app/core/       config, db, security, rbac, deps, errors, logging,
                middleware, pagination
app/db/         24 ORM models, seed script, 12-document demo corpus
app/providers/  base protocols, llm, embeddings, vector_store, blob,
                azure_auth, registry
app/services/   agent_graph, runner, rag, chunking, guardrails,
                evaluation, costs, monitoring, audit, tools
app/api/routes/ 14 routers, 57 OpenAPI paths
app/worker.py   periodic metric collection, alerting, ingestion retry
tests/          102 tests
```

**Modules:** auth, users, agents, agent runs, models, prompts, documents, RAG,
guardrails, evaluations, monitoring, costs, audit, health.

### Frontend — `apps/web`

React 18 · TypeScript (strict) · Vite · Tailwind · TanStack Query · Zustand · Recharts

17 routes: Login, Overview, Agents, Agent detail, Runs, Run inspector, RAG,
Documents, Prompts, Models, Azure Monitor, Evaluations, Guardrails, Cost & Usage,
Alerts, Audit Logs, Settings, plus a 404.

Dark-first Azure-inspired command centre. Every list page implements loading
skeletons, empty states, error states with retry, search, sort and pagination.
Keyboard-navigable with a skip link and visible focus rings.

### Infrastructure

- `docker-compose.yml`: postgres, redis, qdrant, migrate, api, seed, worker, web
- `infrastructure/bicep/main.bicep` + dev/staging/production parameter files
- `.github/workflows/`: `ci.yml`, `docker.yml`, `deploy.yml`
- `scripts/dev.sh` and a `Makefile` wrapping every common task

### Documentation

README, ARCHITECTURE, API, SECURITY, DEVELOPMENT, TESTING, DEPLOYMENT, AZURE,
TROUBLESHOOTING, CONTRIBUTING, and this report.

---

## 3. Notable engineering decisions

**Signed hashing removed from the local embedding.** The first implementation
used signed hashed features (collisions cancel in expectation). In practice it
produced negative cosine scores for short queries and pushed the correct document
out of the top-K — "What caused incident 2043?" ranked the incident document
fourth. Switching to unsigned weights in a 768-dim space with double-weighted
bigrams fixed the ranking for every seeded question. The integration test now
asserts the incident document ranks first, so this cannot silently regress.

**The local LLM does not append a disclaimer to its answer.** It originally
prefixed "Based on the retrieved documents:" and appended a provider note. Both
dragged groundedness scores down, because the evaluator correctly saw ungrounded
terms in the answer. The note moved to `ChatResult.raw` and shows in the run
trace instead. Evaluation now scores the answer, not the boilerplate.

**Synchronous SQLAlchemy.** The workload is request/response with short queries.
Async adds session-lifecycle complexity and a second class of driver bugs for no
measurable gain at this scale.

**An acyclic agent graph.** Retries and model fallback are bounded counters
inside the `generate` node rather than graph cycles. An agent that cannot loop
cannot burn budget in a loop, and termination is structural rather than a guard
someone can remove.

**Cost computed at write time.** Repricing a model must not rewrite last
quarter's spend. A unit test asserts the calculation is configuration-driven.

**Not Celery.** The job set is small, periodic and idempotent. `app/worker.py` is
a signal-handling loop; `run_once()` is designed to drop into Celery beat when
the workload justifies a broker.

---

## 4. Bugs found and fixed during the build

| Bug | Cause | Fix |
|---|---|---|
| App failed to import — `Cannot specify Depends in Annotated and default value together` | Routes used `user: CurrentUser = Depends(require_permission(...))`, and `CurrentUser` already carries a `Depends` | Changed to `user: User = Depends(...)` in all 8 route files |
| 500 on any validation error with a custom validator | Pydantic puts the original `ValueError` object in `ctx`, which is not JSON-serialisable | Handler now extracts `loc`, `msg`, `type` and stringifies |
| Retrieval ranked the wrong document first | Signed hashed embeddings (see above) | Unsigned weights, 768 dimensions, bigrams weighted 2× |
| Low groundedness scores on correct answers | Local LLM appended boilerplate to the answer text | Moved the note into the trace |
| Alembic migration failed at runtime — `NameError: name 'app' is not defined` | Autogenerate rendered `app.core.db.GUID()` without importing the module | Added the import to `script.py.mako` and the generated revision |
| `email-validator is not installed` | `EmailStr` needs the extra | Declared through project dependencies |
| Bundle over 500 kB in one chunk | Recharts bundled with app code | `manualChunks` splits react, charts and query vendors |
| Lint failure on `ui.tsx` | `react-refresh/only-export-components` with `--max-warnings 0` | Scoped override with a written justification |

---

## 5. Known limitations

**Functional**

1. No OCR — scanned PDFs fail ingestion with an explanatory message.
2. Ingestion is synchronous within the upload request. Large corpora should move
   to the worker queue.
3. Evaluation runs synchronously; a large dataset will hold the request open.
4. No WebSocket or SSE — the dashboard polls (Overview every 60s, health every 30s).
5. Agent memory is a configuration flag; conversational memory is not implemented.
6. Azure AI Search is provisioned by the template but not wired into retrieval.

**Operational**

7. The rate limiter is per-process. N replicas means N times the intended limit.
8. No refresh-token rotation and no server-side JWT revocation.
9. The worker is a single-replica timer loop, not a distributed scheduler.

**Security** — see `docs/SECURITY.md` § "What is NOT covered" for the full list.
The headline items: guardrails are heuristics, there is no indirect
prompt-injection defence, no MFA/SSO, and no penetration test has been performed.

---

## 6. Definition of done — honest assessment

| Criterion | Status |
|---|---|
| Frontend builds | ✅ Verified |
| Backend starts | ✅ Verified |
| Migrations run | ✅ Verified, including down and up again |
| Seed data loads | ✅ Verified |
| OpenAPI docs work | ✅ Verified, 57 paths |
| Authentication works | ✅ Verified, JWT and API key |
| RBAC works | ✅ Verified across four roles |
| Agent creation works | ✅ Verified |
| Agent execution works locally | ✅ Verified, full nine-node trace |
| RAG ingestion works | ✅ Verified, 12 documents indexed |
| RAG retrieval works | ✅ Verified, with ranking assertions |
| Document management works | ✅ Verified |
| Prompt versioning works | ✅ Verified |
| Model management works | ✅ Verified |
| Evaluation workflow works | ✅ Verified |
| Guardrail workflow works | ✅ Verified |
| Cost tracking works | ✅ Verified |
| Azure monitoring adapter works | ⚠️ Local collector verified; Azure Monitor not verified |
| Health dashboard works | ✅ Verified |
| Audit logs work | ✅ Verified, including secret redaction |
| Unit tests pass | ✅ 102 backend, 24 frontend |
| Integration tests pass | ✅ Included in the 102 |
| E2E tests pass | ❌ Written, not executed — no browser available |
| CI passes | ❌ Workflows written, never run |
| Docker Compose starts | ❌ Not verified — Docker unavailable |
| Production configuration exists | ✅ Present and validated by `validate_production()` |
| Infrastructure-as-code is valid | ⚠️ Written; never deployed or `what-if`-ed |
| No secrets committed | ✅ Verified — only `.env.example` |
| No TODO placeholders | ✅ Verified — none in the source |
| README has exact setup instructions | ✅ Verified against the actual scripts |

**23 of 29 fully verified. 3 partially. 3 not verified.**

---

## 7. Next steps

**Before any deployment**

1. Run `docker compose up` and fix whatever surfaces.
2. Install Playwright browsers and run the E2E suite.
3. Push to GitHub and let CI run end to end.
4. `az deployment group what-if` against a dev resource group.

**Then, in priority order**

5. Move ingestion and evaluation to the worker queue.
6. Move rate limiting to Redis before scaling past one replica.
7. Wire Entra ID SSO and enable MFA for human users.
8. Replace the lexical evaluator with an LLM judge and re-baseline thresholds.
9. Add OCR for scanned documents.
10. Commission an independent security review.
