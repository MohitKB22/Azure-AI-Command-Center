# Development

## Prerequisites

Python 3.11+ (3.12 recommended), Node 20+, and optionally Docker for the full stack.

## Setup

```bash
./scripts/dev.sh setup   # venv, deps, .env, migrations, demo data
./scripts/dev.sh api     # terminal 1 — http://localhost:8000/docs
./scripts/dev.sh web     # terminal 2 — http://localhost:5173
```

`make setup` / `make api` / `make web` do the same thing.

## Layout

```
apps/api/app/
  core/       config, db, security, rbac, deps, errors, logging, middleware,
              pagination — no business logic lives here
  db/         SQLAlchemy models, seed data, demo corpus
  providers/  external dependencies behind protocols (local | azure)
  services/   business logic: agent_graph, runner, rag, chunking, guardrails,
              evaluation, costs, monitoring, audit, tools
  api/routes/ thin HTTP layer: validate, authorise, delegate, audit
  schemas.py  every request and response contract
apps/web/src/
  components/ ui.tsx (shared primitives), Layout.tsx
  pages/      one file per route
  lib/        api client, types, formatters, hooks
  store/      Zustand session state
```

Dependency direction is one-way: `routes → services → providers/db`. A service
never imports a route; a provider never imports a service.

## Adding an endpoint

1. **Schema** — request and response models in `app/schemas.py`, with bounds.
2. **Service** — the logic in `app/services/`, raising `AppError` subclasses.
3. **Route** — in `app/api/routes/`, with `Depends(require_permission(...))` and
   an `audit.record(...)` call for any mutation.
4. **Register** — include the router in `app/api/router.py` if it is new.
5. **Test** — success, permission denied, validation failure.
6. **Frontend** — add the type to `src/lib/types.ts`, call it with
   `useQuery`/`useMutation`, and handle loading, empty and error states.

## Adding a provider

Implement the protocol in `app/providers/base.py`, register it in
`app/providers/registry.py`, and add the selector to `Settings`. Nothing else
changes — services depend on the protocol, not the implementation.

## Database changes

```bash
cd apps/api
# edit app/db/models.py, then:
alembic revision --autogenerate -m "add widget table"
# review the generated file — autogenerate misses server defaults,
# check constraints and index renames
alembic upgrade head
alembic check     # confirms models and migration agree
```

Verify reversibility before committing:

```bash
alembic downgrade -1 && alembic upgrade head
```

Prefer additive migrations. During a rolling deploy the old revision keeps
serving traffic, so a dropped column takes it down. Add, backfill, switch reads,
then drop in a later release.

## Conventions

**Python** — ruff (line length 100), type hints on public functions, docstrings
that explain *why* rather than restating the signature. Business rules raise
typed errors; routes never build error responses by hand.

**TypeScript** — strict mode, no `any` in domain types, every list page handles
loading, empty and error states. Server state belongs to TanStack Query; only
session state goes in Zustand.

**Naming** — permissions `resource:action`, audit actions `resource.verb`, tables
plural snake_case, React components PascalCase.

## Working offline vs. against Azure

```bash
# offline (default)
LLM_PROVIDER=local EMBEDDING_PROVIDER=local VECTOR_STORE=local

# Azure OpenAI for generation, everything else local
LLM_PROVIDER=azure
AZURE_OPENAI_ENDPOINT=https://<resource>.openai.azure.com
AZURE_OPENAI_CHAT_DEPLOYMENT=gpt-4o
AZURE_OPENAI_API_KEY=...        # or AZURE_USE_MANAGED_IDENTITY=true
```

Switching embedding providers changes the vector space. Reprocess every document
afterwards (`POST /documents/{id}/reprocess`) or retrieval will silently degrade
— old and new vectors are not comparable.

## Useful commands

```bash
make check                       # the full CI gate locally
cd apps/api && ruff check --fix .
cd apps/api && pytest -k guardrail -v
cd apps/api && python -m app.db.seed --reset
cd apps/api && python -m app.worker
cd apps/web && npm run typecheck
```

## Debugging

- `DEBUG=true` raises log verbosity; `SQL_ECHO=true` prints every statement.
- Every response carries `X-Request-ID`. Grep the JSON logs for it to get the
  full server-side story for one request.
- An agent run's `trace` records the active providers, the routing decision, the
  retrieval configuration and the attempt count — start there when a run behaves
  unexpectedly rather than adding print statements.
