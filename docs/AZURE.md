# Azure integration

## Resources and why each exists

| Resource | Used for | Required? |
|---|---|---|
| Azure OpenAI | Chat generation and embeddings | Only when `LLM_PROVIDER`/`EMBEDDING_PROVIDER=azure` |
| Azure AI Search | Optional hybrid retrieval alongside the vector store | No |
| Blob Storage | Original uploaded documents | Only when `BLOB_PROVIDER=azure` |
| PostgreSQL Flexible Server | All relational data | Yes, outside local development |
| Key Vault | `SECRET_KEY` and any remaining secrets | Yes in production |
| Container Apps | API, web and worker hosting | Yes |
| Container Registry | Image storage | Yes |
| Application Insights + Log Analytics | Telemetry and log retention | Yes in production |
| Managed Identity | Credential-free access to all of the above | Yes |

## Identity model

The API runs as a **user-assigned Managed Identity** holding one narrowly scoped
role per resource:

| Resource | Role | Why not broader |
|---|---|---|
| Key Vault | Key Vault Secrets User | Read secrets; cannot manage the vault |
| Storage | Storage Blob Data Contributor | Read/write blobs; cannot change account settings |
| Azure OpenAI | Cognitive Services OpenAI User | Call deployments; cannot create or delete them |
| AI Search | Search Index Data Contributor | Manage documents; cannot manage the service |
| Container Registry | AcrPull | Pull images; cannot push |

Local authentication is disabled where the platform supports it:
`Storage.allowSharedKeyAccess = false`, `OpenAI.disableLocalAuth = true`,
`PostgreSQL.passwordAuth = Disabled`. There is no static credential to rotate or
leak — that is the point.

## Switching from local to Azure

Do this one provider at a time so a failure has one obvious cause.

### 1. Azure OpenAI for generation

```bash
LLM_PROVIDER=azure
AZURE_OPENAI_ENDPOINT=https://<resource>.openai.azure.com
AZURE_OPENAI_CHAT_DEPLOYMENT=gpt-4o
AZURE_OPENAI_API_VERSION=2024-10-21
AZURE_USE_MANAGED_IDENTITY=true      # or AZURE_OPENAI_API_KEY locally
```

Verify: run an agent. `trace.providers.llm` should read `azure`, and answers
should be generative rather than extracted sentences.

### 2. Azure OpenAI for embeddings

```bash
EMBEDDING_PROVIDER=azure
AZURE_OPENAI_EMBEDDING_DEPLOYMENT=text-embedding-3-large
EMBEDDING_DIM=3072
```

**Reprocess every document afterwards.** Vectors from different models are not
comparable, so retrieval silently degrades if you skip this:

```bash
for id in $(curl -s -H "Authorization: Bearer $TOKEN" \
  "$API/api/v1/documents?page_size=200" | jq -r '.items[].id'); do
  curl -s -X POST -H "Authorization: Bearer $TOKEN" \
    "$API/api/v1/documents/$id/reprocess" > /dev/null
done
```

### 3. Blob Storage

```bash
BLOB_PROVIDER=azure
AZURE_STORAGE_ACCOUNT_URL=https://<account>.blob.core.windows.net
AZURE_STORAGE_CONTAINER=documents
```

Existing local files are not migrated. Either copy `var/blobs/` into the
container with `azcopy`, or re-upload.

### 4. Qdrant

```bash
VECTOR_STORE=qdrant
QDRANT_URL=https://<host>:6333
QDRANT_API_KEY=<key>
```

Then reprocess documents to populate the collection. Chunks stay in PostgreSQL;
Qdrant holds a mirror of the vectors with payloads.

### 5. Azure Monitor

```bash
APPLICATIONINSIGHTS_CONNECTION_STRING=<connection string>
ENVIRONMENT=production
```

`get_collector()` switches to `AzureMonitorCollector` automatically. Each
`azure_resources` row needs `details.resource_id` set to the full ARM resource ID
before live metrics can be read; rows without one stay `not_configured`.

Requires the optional extra: `pip install azure-monitor-query azure-identity`.

## Cost control

- Set `input_cost_per_1k` and `output_cost_per_1k` on every catalogue model. They
  drive all cost maths; a model priced at zero silently reports zero spend.
- Create budgets per team. The worker raises a warning alert at the threshold.
- The biggest lever is retrieval size. Dropping `top_k` from 12 to 5 typically
  removes more spend than any model change, because retrieved context dominates
  prompt tokens.
- Azure OpenAI capacity is per-deployment TPM. The Bicep parameters set modest
  defaults; raise `capacity` deliberately rather than by trial and error.

## Regional considerations

Model availability varies by region, and `gpt-4o` version numbers differ between
regions. Check availability before deploying, and pin versions in
`openAiDeployments` rather than accepting whatever is current — the template sets
`versionUpgradeOption: OnceCurrentVersionExpired` so a model does not change
underneath a validated evaluation baseline.

## What has not been verified

No resource in this repository has been provisioned. Specifically unverified:

- Bicep deployment succeeds end to end
- Azure OpenAI request/response handling against a live endpoint
- Managed Identity token acquisition
- Blob Storage read/write through `DefaultAzureCredential`
- Qdrant collection creation and search
- Azure Monitor metric queries
- PostgreSQL Entra authentication from Container Apps

The code follows documented API contracts, but "follows the documentation" and
"works" are different claims. Deploy to `dev` first.
