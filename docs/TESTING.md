# Testing

## Layers

| Layer | Location | Count | Runs against |
|---|---|---|---|
| Backend unit | `apps/api/tests/test_unit_core.py` | 47 | Pure functions, no I/O |
| Backend integration | `apps/api/tests/test_api_integration.py` | 55 | Real app, real database, real ingestion |
| Frontend unit | `apps/web/src/**/*.test.ts(x)` | 24 | jsdom + Testing Library |
| End-to-end | `apps/web/e2e/` | 11 specs | Playwright against a running stack |

Backend tests use an isolated SQLite file and a temporary blob directory, with
local providers selected. No network access and no Azure credentials are needed.

## Running

```bash
# everything
make test

# backend only
cd apps/api && pytest -q
cd apps/api && pytest --cov=app --cov-report=term-missing
cd apps/api && pytest tests/test_unit_core.py::TestGuardrails -v

# frontend only
cd apps/web && npm test
cd apps/web && npm run test:watch

# the full CI gate locally: lint, types, tests, build
make check
```

### End-to-end

E2E needs the API running with seed data. Playwright starts the web dev server
itself.

```bash
# terminal 1
cd apps/api && python -m app.db.seed --reset && uvicorn app.main:app --port 8000

# terminal 2
cd apps/web && npx playwright install --with-deps chromium && npm run e2e
```

`E2E_NO_SERVER=1` skips starting the dev server if you already have one.

## What the integration tests actually prove

These assert behaviour, not just status codes:

- **Auth** — wrong password and unknown user return the same 401 message; a
  revoked API key stops working immediately; missing credentials are 401.
- **RBAC** — a viewer cannot write agents or read users; an engineer cannot
  create users; a viewer can still read agents.
- **Agent lifecycle** — create → edit (version 2) → list versions → roll back
  (version 3, original values restored) → archive → 404.
- **Execution** — a run produces exactly the nine expected graph nodes in order;
  a grounded answer carries citations; an injection attempt is `blocked` before
  the model is called; a disabled agent cannot run.
- **Ingestion** — an uploaded document reaches `indexed` with chunks; a query
  retrieves it by content; duplicate content is rejected with 409; unsupported
  extensions and empty files are rejected.
- **Retrieval quality** — asking about incident 2043 ranks the incident document
  first; raising the similarity threshold strictly reduces results.
- **Prompts** — versioning, variable extraction, rendering with missing-variable
  reporting, rollback, and refusal to promote an unapproved version.
- **Models** — only one default at a time; a model in use cannot be deleted.
- **Evaluation** — every dataset item is scored; the adversarial item scores
  `safety = 0.0`; CSV export includes the metric columns.
- **Honesty** — unconfigured Azure resources report `not_configured` with zero
  metrics; an issued API key never appears in the audit log.

## Deterministic by construction

The local providers are pure functions of their input:

- `LocalHashEmbedding` produces identical vectors for identical text.
- `LocalGroundedLLM` extracts sentences by a fixed scoring rule.
- Evaluation metrics are lexical, so scores do not drift between runs.

That means a failing test is a real regression, not model variance.

## Migration verification

CI runs, and you should run locally before any schema change:

```bash
cd apps/api
alembic upgrade head      # from empty
alembic downgrade base    # full teardown
alembic upgrade head      # rebuild
alembic check             # models match the migration
```

## Coverage

```bash
cd apps/api && pytest --cov=app --cov-report=html
open htmlcov/index.html
```

Deliberately not covered: `AzureOpenAIChat`, `AzureOpenAIEmbedding`,
`AzureBlobStore`, `QdrantVectorStore`, `AzureMonitorCollector`. These require live
services; mocking them would test the mock rather than the integration. They are
listed as "not verified" in BUILD_REPORT.md rather than covered by a fake.

## Adding a test

Fixtures available: `client`, `db`, `admin_headers`, `engineer_headers`,
`viewer_headers`, `enabled_agent_id`.

```python
class TestMyFeature:
    def test_permission_is_enforced(self, client, viewer_headers):
        response = client.post("/api/v1/my-thing", headers=viewer_headers, json={})
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "permission_denied"
```

Every new endpoint needs at least: a success case, an authorization-denied case,
and a validation-failure case.
