# Security

## Scope of this document

What the platform actually enforces, what it deliberately does not, and where the
sharp edges are. It is written to be useful in a review, not reassuring.

## Controls implemented

### Authentication

- JWT (HS256) access tokens with `exp`, `iat`, `jti` and issuer; verification
  requires both `sub` and `exp`.
- API keys: 32 bytes of `secrets.token_urlsafe`, SHA-256 hashed at rest,
  compared with `hmac.compare_digest`, revocable and optionally expiring.
- Passwords: PBKDF2-SHA256 at 390,000 rounds, per-password salt, via passlib.
  bcrypt hashes remain verifiable so the backend can change without a reset.
- Login returns an identical error for unknown user and wrong password, so the
  endpoint does not enumerate accounts.
- Failed logins are audited with the attempted address and source IP.

### Authorization

- Five roles map to static permission sets — authorization never needs a
  database round-trip and cannot drift per-request.
- Every route declares `Depends(require_permission("resource:action"))`. There is
  no implicit-allow path; a route without a permission dependency does not exist.
- Self-protection rules: an admin cannot remove their own admin role or
  deactivate their own account.

### Transport and headers

`X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`,
`Referrer-Policy: strict-origin-when-cross-origin`,
`Cross-Origin-Opener-Policy: same-origin`, `Permissions-Policy` disabling camera,
microphone and geolocation, and HSTS outside local. CORS uses an explicit origin
allowlist with a bounded method and header set — never `*`.

### Input handling

- Pydantic v2 validates every request body, with bounded string lengths and
  numeric ranges.
- SQL injection: SQLAlchemy parameter binding throughout. No string-built SQL.
- XSS: React escapes by default; no `dangerouslySetInnerHTML` anywhere.
- Uploads: extension allowlist, size cap (before buffering, via
  `Content-Length`), path-separator and traversal rejection, checksum dedupe.
  There is a documented integration point for malware scanning before persist.
- Path traversal in blob keys is blocked by resolving and re-checking the prefix.
- Rate limiting per API key, JWT or IP with a `Retry-After` response.

### Secret handling

- No secret has a working default. `Settings.validate_production()` refuses to
  start production with the development key, a SQLite URL, or `DEMO_MODE=true`.
- The structured logger redacts by key name (`password`, `secret`, `token`,
  `api_key`, `authorization`, `connection_string`, `client_secret`) and by value
  shape (`Bearer …`, `sk-…`, `AccountKey=…`).
- Audit `changes` are passed through the same redaction before persisting. A test
  asserts that an issued API key never appears in the audit log.
- In Azure: Managed Identity everywhere. Storage sets
  `allowSharedKeyAccess: false`, Azure OpenAI sets `disableLocalAuth: true`,
  PostgreSQL sets `passwordAuth: Disabled`. There is no credential to leak.
- The browser keeps the JWT in memory only — never `localStorage` — so an
  injected script cannot read it from storage. The cost is re-authentication per
  tab, which is the right trade for a control plane.

### AI-specific controls

Detection, policy and enforcement are separate by design:

| Layer | Implementation |
|---|---|
| Detection | Regex rules for instruction override, system-prompt exfiltration, role hijack, credential probing, encoded payloads; PII/secret patterns |
| Policy | Per-agent `GuardrailPolicy`: block-on-injection, redact PII, input size cap, banned phrases, tool allowlist, domain allowlist, require citations |
| Enforcement | Graph nodes that halt execution; `filter_tools` at execution time, not just configuration time |

- Tools are a closed registry. The calculator parses with an AST allowlist and
  never calls `eval`. No tool performs network I/O.
- The local LLM is extractive, so offline demos cannot fabricate facts or
  citations.
- Output guardrails can withhold a response entirely, including when a policy
  requires citations and none were retrieved.

### Auditability

Append-only `audit_logs` with actor, action, resource, outcome, IP, request ID
and a redacted change set. Writes happen in the same transaction as the mutation,
so an audit gap implies a rolled-back change.

## What is NOT covered

Read this section before trusting the platform with anything sensitive.

1. **Guardrails are heuristics.** Regex-based injection detection catches common
   phrasings. A motivated attacker will bypass it with paraphrase, encoding or
   multi-turn setup. Pair it with Azure AI Content Safety, minimal tool grants,
   and human confirmation for irreversible actions.
2. **No indirect prompt-injection defence.** Retrieved document text is inserted
   into the model context. A poisoned document can carry instructions. Treat
   every corpus as untrusted input.
3. **The rate limiter is per-process.** With more than one replica the effective
   limit multiplies. Move it to Redis or the ingress before scaling out.
4. **No refresh-token rotation or server-side revocation.** Access tokens are
   valid until they expire. Shorten `ACCESS_TOKEN_TTL_MINUTES` if that window
   matters; add a deny-list if you need immediate revocation.
5. **No MFA and no Entra ID SSO wiring.** The configuration surface is present
   (`AZURE_USE_MANAGED_IDENTITY`, OIDC-ready settings) but the OIDC login flow is
   not implemented.
6. **No field-level encryption.** Document text and extracted content sit in the
   database in plaintext, protected by storage-level encryption only.
7. **No malware scanning.** The integration point is marked in
   `app/api/routes/documents.py`; nothing is wired to it.
8. **CSRF is not applicable as configured** because authentication is a bearer
   header, not a cookie. If you switch to cookie sessions, you must add CSRF
   protection.
9. **Penetration testing has not been performed.** No third party has reviewed
   this code.

## Before production

- [ ] Generate `SECRET_KEY` with `python -c "import secrets; print(secrets.token_urlsafe(48))"`
- [ ] `ENVIRONMENT=production`, `DEMO_MODE=false`, PostgreSQL `DATABASE_URL`
- [ ] Managed Identity for every Azure provider; no API keys in configuration
- [ ] Private endpoints for PostgreSQL, Storage, Key Vault, Azure OpenAI
- [ ] Distributed rate limiting; WAF in front of the ingress
- [ ] Entra ID SSO and MFA for human users; API keys only for automation
- [ ] Log shipping to Log Analytics with alerting on `permission_denied` spikes
- [ ] Delete or rotate every seeded demo account
- [ ] Independent security review

## Reporting a vulnerability

Do not open a public issue. Contact the platform team directly with reproduction
steps and the affected version.
