# Troubleshooting

Every API response carries `X-Request-ID`. Start by grepping the JSON logs for it.

## Setup

**`./scripts/dev.sh setup` fails installing dependencies**
Check `python3 --version` (3.11+) and `node --version` (20+). Delete
`apps/api/.venv` and `apps/web/node_modules` and retry.

**`ModuleNotFoundError: No module named 'app'`**
Commands must run from `apps/api`, or the package must be installed with
`pip install -e .`.

**`email-validator is not installed`**
`pip install -e ".[dev]"` from `apps/api` — `pydantic[email]` is pulled in by the
project dependencies.

## API

**Port 8000 already in use**
`lsof -ti:8000 | xargs kill` or run with `--port 8001` and set
`VITE_API_BASE_URL` to match.

**401 on every request after a while**
Access tokens expire after `ACCESS_TOKEN_TTL_MINUTES` (default 8 hours), and the
token is held in memory only — a page reload signs you out by design. Sign in
again.

**403 with `permission_denied`**
Expected for the role. Compare `GET /auth/me` against `GET /users/roles`. Viewer
cannot write; engineer cannot manage users.

**429 `rate_limited`**
Over `RATE_LIMIT_PER_MINUTE`. Raise it for local development. If you are running
multiple replicas, note the limiter is per-process.

**500 on startup in production**
`Settings.validate_production()` refuses to start with the development
`SECRET_KEY`, a SQLite `DATABASE_URL`, or `DEMO_MODE=true`. The log names the
exact problem.

## Database

**`alembic upgrade head` fails with "Can't locate revision"**
The database has a revision the code does not. Either check out the matching
commit or, in local development, `python -m app.db.seed --reset`.

**`alembic check` reports changes after editing models**
Expected — generate a migration: `alembic revision --autogenerate -m "..."`.

**SQLite "database is locked"**
Two processes writing at once. Stop the worker, or move to PostgreSQL
(`docker compose up -d postgres`).

**Migration succeeds but the app cannot connect**
Confirm the driver in the URL: `postgresql+psycopg://…`, not `postgres://`.

## Documents and retrieval

**Upload returns 422 "Unsupported file type"**
Allowed: `.pdf .txt .md .csv .json .docx`. Extend
`ALLOWED_UPLOAD_EXTENSIONS` — and add an extractor in `app/services/chunking.py`,
otherwise ingestion will fail later with an unhelpful error.

**Upload returns 409**
Byte-identical content is already indexed. Change the content or delete the
existing document.

**Document status is `failed`**
The reason is in `error_message` on the document. Most common: a scanned PDF with
no embedded text. OCR is an integration point, not a built-in.

**A RAG query returns no chunks**
In order: is any document `indexed`? Is `similarity_threshold` too high (try
0.0)? Does the query share vocabulary with the corpus? The local embedding is
lexical — synonyms do not match. Use `EMBEDDING_PROVIDER=azure` for semantic
retrieval.

**Retrieval got worse after switching embedding providers**
Old vectors are in the previous model's space. Reprocess every document — see
AZURE.md.

**The answer says it could not find supporting content**
That is the local provider refusing to answer from memory. It is correct
behaviour, not a bug. Either the retrieval returned nothing useful or the
question is not covered by the corpus.

## Agents

**Run returns 422 "Agent is disabled"**
Enable it on the agent page, or use `POST /agents/{id}/toggle`.

**Run status is `blocked`**
An input or output guardrail matched. Open the run trace: the
`guardrail_input`/`guardrail_output` step lists the rule. Test the exact text at
`POST /guardrails/test`.

**Run status is `failed` with `generation_failed`**
Both the primary and fallback model failed. In Azure mode, check the endpoint,
deployment name and quota. `error_message` carries the provider's reason.

**`used_fallback: true` unexpectedly**
The primary model errored through its retry budget. Check quota and deployment
health.

**Tokens are zero on a blocked run**
Correct — the model was never called. That is the whole point of blocking at the
input guardrail.

## Frontend

**Blank page after `npm run dev`**
Open the browser console. Most often the API is not running: the login page will
report "Unable to reach the API".

**CORS errors**
Add the exact browser origin to `CORS_ORIGINS` (scheme, host and port) and
restart the API.

**Charts render empty**
No usage in the selected window. Run an agent, or reseed with
`python -m app.db.seed --reset`.

**`npm run build` fails with type errors**
Run `npm run typecheck` for the full list. `tsc -b` runs before the bundler on
purpose — a type error should fail the build, not ship.

## Docker

**`docker compose up` — API restarts repeatedly**
`docker compose logs api`. Usually the migration service failed; check
`docker compose logs migrate`.

**Web container shows a blank page**
`VITE_API_BASE_URL` is baked in at build time, not read at runtime. Rebuild with
the right value: `docker compose build --build-arg VITE_API_BASE_URL=... web`.

**Volumes hold stale data**
`docker compose down -v` removes them.

## Azure

**`provider_not_configured` (503)**
An Azure provider is selected without its configuration. The message names the
missing variable.

**`provider_error` (502)**
The upstream call failed. Check endpoint, deployment name, quota and network
path. Enable `DEBUG=true` for the full exception.

**Azure resources all show `not_configured`**
Expected without credentials. The platform reports zeros rather than inventing
metrics. Set `APPLICATIONINSIGHTS_CONNECTION_STRING`, `ENVIRONMENT=production`,
and `details.resource_id` on each row.

**`azure-identity is not installed`**
`pip install -e ".[azure]"` from `apps/api`.
