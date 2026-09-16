# Deployment

> Nothing in this repository has been deployed to Azure. The templates and
> workflows below are written against documented Azure behaviour and validated
> only by inspection. Run `az deployment group what-if` and deploy to `dev`
> before trusting them.

## Environments

| | dev | staging | production |
|---|---|---|---|
| PostgreSQL | Burstable B1ms, 32 GB | Burstable B1ms, 32 GB | GeneralPurpose D2ds_v5, ZoneRedundant HA |
| Backups | 7 days | 7 days | 35 days, geo-redundant |
| Public network access | Enabled | Enabled | Disabled (private endpoints) |
| Key Vault purge protection | Off | Off | On |
| Search | basic, 1 replica | basic | standard, 2 replicas |
| `DEMO_MODE` | true | false | false (startup refuses otherwise) |

## Prerequisites

1. Azure subscription with Contributor on the target resource group.
2. An Entra app registration with a federated credential for GitHub OIDC — no
   client secret is stored anywhere.
3. Repository configuration:

   **Secrets**: `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID`

   **Variables**: `AZURE_RESOURCE_GROUP`, `ACR_NAME`, `ACR_LOGIN_SERVER`,
   `API_CONTAINER_APP`, `WEB_CONTAINER_APP`, `MIGRATION_JOB_NAME`, `API_BASE_URL`

## Infrastructure

```bash
export KEYVAULT_ADMIN_OBJECT_ID=$(az ad group show --group "AI Platform Admins" --query id -o tsv)

az deployment group what-if \
  --resource-group rg-aicc-dev \
  --template-file infrastructure/bicep/main.bicep \
  --parameters infrastructure/bicep/params/dev.bicepparam

az deployment group create \
  --resource-group rg-aicc-dev \
  --template-file infrastructure/bicep/main.bicep \
  --parameters infrastructure/bicep/params/dev.bicepparam
```

Provisions: user-assigned Managed Identity, Log Analytics, Application Insights,
Key Vault (RBAC), Storage with `documents` container, Azure OpenAI with model
deployments, AI Search, PostgreSQL Flexible Server (Entra auth only), Container
Apps environment, and Container Registry — plus one narrowly scoped role
assignment per resource for the identity.

Or use the `Deploy` workflow with `deploy_infrastructure: true`, which runs
`validate` and `what-if` before `create`.

## Application

The `Deploy` workflow:

1. Builds both images with `az acr build`.
2. Runs migrations as a **one-off Container App Job** before the new revision
   takes traffic.
3. Updates the API and web Container Apps with a SHA-suffixed revision.
4. Polls `/health/ready` for up to five minutes.
5. On failure, shifts 100% of traffic back to the previous revision.

**Why this rollback is safe:** migrations are additive, so the previous revision
still works against the migrated schema. That property is what makes traffic
shifting a real rollback rather than a hope. Preserve it — never drop or rename a
column in the same release that stops using it.

## Configuration in Azure

Set on the API Container App:

```
ENVIRONMENT=production
DEMO_MODE=false
DATABASE_URL=postgresql+psycopg://<identity>@<server>.postgres.database.azure.com:5432/aicc
SECRET_KEY=<Key Vault reference>
CORS_ORIGINS=https://<your-web-host>
LLM_PROVIDER=azure
EMBEDDING_PROVIDER=azure
BLOB_PROVIDER=azure
VECTOR_STORE=qdrant           # or keep 'local' to start
AZURE_USE_MANAGED_IDENTITY=true
AZURE_OPENAI_ENDPOINT=<from Bicep output>
AZURE_OPENAI_CHAT_DEPLOYMENT=gpt-4o
AZURE_OPENAI_EMBEDDING_DEPLOYMENT=text-embedding-3-large
AZURE_STORAGE_ACCOUNT_URL=<from Bicep output>
APPLICATIONINSIGHTS_CONNECTION_STRING=<from Bicep output>
```

`SECRET_KEY` should be a Key Vault reference, not a literal. The application
refuses to start in production with the development key, a SQLite URL, or
`DEMO_MODE=true` — that check is in `Settings.validate_production()`.

## Scaling

- **API**: stateless, scale on HTTP concurrency. Before running more than one
  replica, move rate limiting to Redis or the ingress — the built-in limiter is
  per-process, so N replicas means N times the intended limit.
- **Worker**: exactly one replica. Its jobs are idempotent but duplicated alert
  raising is noise.
- **PostgreSQL**: read replicas are unnecessary at this scale; add connection
  pooling (PgBouncer) before adding replicas.

## Post-deployment checks

```bash
curl -sf $API_BASE_URL/health/ready | jq
# expect: status ready, database up, providers azure, no configuration_warnings

curl -sf $API_BASE_URL/openapi.json | jq '.paths | length'
```

Then sign in, open Overview, and confirm Azure resources report `live` rather
than `not_configured`.

## Rollback

Automatic on a failed health check. Manual:

```bash
az containerapp revision list --name $API_CONTAINER_APP \
  --resource-group $RG --query "[].{name:name,active:properties.active}" -o table

az containerapp ingress traffic set --name $API_CONTAINER_APP \
  --resource-group $RG --revision-weight <previous-revision>=100
```

Database rollback is deliberately manual. `alembic downgrade` on a live database
is a data-loss operation; restore from a point-in-time backup instead.

## Operational monitoring

Alert on: `/health/ready` failing, error rate above 5% over 15 minutes, p95
latency above 5 seconds, budget utilisation above 80%, and any spike in
`permission_denied` audit entries.
