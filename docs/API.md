# API reference

Base URL: `http://localhost:8000` · API prefix: `/api/v1`
Interactive docs: `/docs` (Swagger) and `/redoc`. OpenAPI JSON: `/openapi.json`.

## Authentication

Two mechanisms, both resolved by the same dependency.

**Bearer JWT — for the UI**

```bash
TOKEN=$(curl -s localhost:8000/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"admin@contoso.com","password":"Passw0rd!Demo"}' | jq -r .access_token)

curl localhost:8000/api/v1/agents -H "Authorization: Bearer $TOKEN"
```

**API key — for CI/CD and integrations**

```bash
KEY=$(curl -s -X POST localhost:8000/api/v1/auth/api-keys \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"name":"github-actions","expires_in_days":90}' | jq -r .key)

curl localhost:8000/api/v1/agents -H "X-API-Key: $KEY"
```

The plaintext key is returned exactly once; only a SHA-256 hash is stored.

## Authorization

Permissions are `<resource>:<action>` where action ∈ `read | write | delete | execute`.

| Role | Summary |
|---|---|
| `admin` | Everything, including users, settings and audit |
| `ai_engineer` | Full agent, model, prompt, document, evaluation and guardrail control; no user management |
| `developer` | Create and run agents, manage prompts, upload documents |
| `analyst` | Read everything operational, run evaluations, read audit |
| `viewer` | Read-only, excluding users and audit |

`GET /api/v1/auth/me` returns the caller's resolved permission list.
`GET /api/v1/users/roles` returns the full matrix.

## Conventions

**Pagination** — every list endpoint accepts `page`, `page_size` (max 200),
`sort_by`, `sort_dir` (`asc|desc`) and `q` (free-text search).

```json
{ "items": [], "total": 128, "page": 1, "page_size": 25, "pages": 6 }
```

**Errors** — one envelope, always.

```json
{
  "error": {
    "code": "permission_denied",
    "message": "Role 'viewer' is not allowed to perform 'agents:write'.",
    "details": null,
    "request_id": "9f2c1b3e4a5d6f70"
  }
}
```

| Code | HTTP | Meaning |
|---|---|---|
| `unauthenticated` | 401 | Missing, invalid or expired credentials |
| `permission_denied` | 403 | Authenticated but not authorised |
| `not_found` | 404 | Resource missing or soft-deleted |
| `conflict` | 409 | Uniqueness or state conflict |
| `payload_too_large` | 413 | Body exceeds `MAX_UPLOAD_BYTES` |
| `validation_error` | 422 | Schema or business-rule violation |
| `rate_limited` | 429 | Over `RATE_LIMIT_PER_MINUTE`; see `Retry-After` |
| `provider_error` | 502 | Upstream provider failed |
| `provider_not_configured` | 503 | Azure provider selected without configuration |

**Correlation** — send `X-Correlation-ID` to trace a multi-request journey. Both
that and `X-Request-ID` come back on every response and appear in every log line.

## Endpoints

### Health (no auth)

| Method | Path | Notes |
|---|---|---|
| GET | `/health/live` | Liveness. Never touches the database. |
| GET | `/health/ready` | Readiness. Verifies the database and reports active providers. |

### Auth

| Method | Path |
|---|---|
| POST | `/auth/login` |
| GET | `/auth/me` |
| POST | `/auth/logout` |
| GET | `/auth/api-keys` |
| POST | `/auth/api-keys` |
| DELETE | `/auth/api-keys/{key_id}` |

### Users — `users:*`

`GET /users` · `GET /users/roles` · `POST /users` · `GET /users/{id}` ·
`PATCH /users/{id}` · `DELETE /users/{id}`

### Overview — `monitoring:read`

`GET /overview?days=14` — KPIs, time series, model usage, agent activity, recent
runs, active alerts and system health in one call.

### Agents — `agents:*`

| Method | Path | Permission |
|---|---|---|
| GET | `/agents` | `agents:read` |
| GET | `/agents/graph-topology` | `agents:read` |
| POST | `/agents` | `agents:write` |
| GET | `/agents/{id}` | `agents:read` |
| PATCH | `/agents/{id}` | `agents:write` |
| DELETE | `/agents/{id}` | `agents:delete` |
| POST | `/agents/{id}/duplicate` | `agents:write` |
| POST | `/agents/{id}/toggle` | `agents:write` |
| GET | `/agents/{id}/versions` | `agents:read` |
| POST | `/agents/{id}/versions/{v}/rollback` | `agents:write` |
| POST | `/agents/{id}/run` | `agents:execute` |

Filters on `GET /agents`: `status_filter`, `environment`, `enabled`.

Any configuration change creates a new version automatically — there is no
separate "publish" step to forget.

### Agent runs — `agents:read`

`GET /runs` (filters: `agent_id`, `status_filter`) · `GET /runs/{id}`

`GET /runs/{id}` returns the full trace: every graph node with duration and
detail, citations with scores, token counts, cost and guardrail outcome.

### Models — `models:*`

`GET /models` (filter `kind=chat|embedding`) · `POST /models` ·
`GET /models/{id}` · `PATCH /models/{id}` · `DELETE /models/{id}`

Deleting a model assigned to an agent returns 422 rather than orphaning it.
Setting `is_default` or `is_fallback` clears the flag on all other models.

### Prompts — `prompts:*`

`GET /prompts` · `POST /prompts` · `GET /prompts/{id}` ·
`POST /prompts/{id}/versions` · `POST /prompts/{id}/rollback/{v}` ·
`POST /prompts/{id}/render` · `POST /prompts/{id}/promote/{v}?environment=` ·
`DELETE /prompts/{id}`

Variables use `{{name}}`. Only `approved` versions may be promoted to production.

### Documents — `documents:*`

`GET /documents` · `POST /documents` (multipart) · `GET /documents/{id}` ·
`GET /documents/{id}/chunks` · `POST /documents/{id}/reprocess` ·
`DELETE /documents/{id}`

```bash
curl -X POST localhost:8000/api/v1/documents \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@policy.pdf" -F "tags=policy,internal"
```

Uploads are validated for extension, size, path traversal and duplicate
checksum. Ingestion runs inline and the response carries the final status.

### RAG — `documents:*`

`GET /rag/stages` · `GET /rag/pipelines` · `POST /rag/pipelines` ·
`PATCH /rag/pipelines/{id}` · `DELETE /rag/pipelines/{id}` · `POST /rag/query`

```bash
curl -X POST localhost:8000/api/v1/rag/query \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"query":"What is the default chunk size?","top_k":5,"generate_answer":true}'
```

The response includes per-stage timings, candidate counts, vector and rerank
scores, and citations.

### Guardrails — `guardrails:*`

`GET /guardrails/policies` · `POST /guardrails/policies` ·
`DELETE /guardrails/policies/{id}` · `GET /guardrails/rules` ·
`POST /guardrails/test` · `GET /guardrails/events`

`POST /guardrails/test` runs the exact code path an agent run uses, so what you
see in the tester is what will happen in production.

### Evaluations — `evaluations:*`

`GET /evaluations/metrics` · `GET /evaluations/datasets` ·
`POST /evaluations/datasets` · `GET /evaluations/runs` ·
`POST /evaluations/runs` · `GET /evaluations/runs/{id}` ·
`GET /evaluations/runs/{id}/export` (CSV)

Metrics: groundedness, relevance, faithfulness, context precision, context
recall, answer correctness, safety, token efficiency, plus an `overall` mean and
`pass_rate`.

### Monitoring — `monitoring:*`

`GET /monitoring/azure-resources` · `POST /monitoring/collect` ·
`GET /monitoring/health` · `GET /monitoring/alerts` ·
`POST /monitoring/alerts/{id}/acknowledge` · `POST /monitoring/alerts/{id}/resolve`

Each resource carries `data_source`: `local` (measured here), `live` (Azure
Monitor) or `none` (unconfigured — values are zero, never invented).

### Costs — `costs:read`

`GET /costs/summary?days=30` · `GET /costs/records`

Summary returns totals, a daily series, breakdowns by model, agent and team, and
budget utilisation.

### Audit — `audit:read`

`GET /audit/logs` (filters: `action`, `resource_type`, `outcome`, `since`) ·
`GET /audit/actions`

## Rate limiting

Fixed window, `RATE_LIMIT_PER_MINUTE` (default 240), keyed by API key, JWT or IP.
Health and docs endpoints are exempt. The limiter is in-process — behind more
than one replica, move it to Redis or the ingress (see DEPLOYMENT.md).
