# Security Guide

Security spans ingress (Layer 1) and safety (Layer 2).

## Authentication

- **Supabase JWT** verified in `app/auth/supabase.py`.
  - HS256 with `SUPABASE_JWT_SECRET`, or
  - RS256/ES256 with `SUPABASE_JWKS_URL` (JWKS fetched + cached, rotated hourly).
- Audience (`SUPABASE_JWT_AUDIENCE`, default `authenticated`) and optional issuer
  are verified. Expired/invalid tokens → `401` with the standard error envelope.
- The verified `Principal` carries `user_id`, `email`, `role`, `tenant_id`,
  `app_metadata`, `user_metadata`, `scopes`.

## Multi-tenancy & isolation

- Tenant is taken from the JWT `app_metadata.tenant_id` (authoritative).
- The `X-Tenant-ID` header is a hint; if it disagrees with the JWT tenant and
  `ENFORCE_TENANT_ISOLATION=true`, the request is rejected (`400 tenant_error`)
  unless the principal is a service account.
- Retrieval enforces isolation at the data layer: **both** dense and sparse
  search filter on `tenant_id`. A tenant can never retrieve another tenant's
  chunks.

## Rate limiting

Token-bucket limiter (`services/rate_limiter.py`), enforced per request:
- **per-user** (`RATE_LIMIT_USER_*`) and
- **per-tenant** (`RATE_LIMIT_TENANT_*`) — both must pass.

Exceeded limits → `429` with a `Retry-After` header. Backend is `memory`
(single process) with a Redis-ready Protocol for multi-replica deployments.

## Input safety (`safety/input_safety.py`)

Screens queries before retrieval/reasoning:
- **LlamaGuard** (production, via Ollama) or **Heuristic** (regex) backend.
- Detects prompt injection, jailbreak attempts, unsafe requests.
- Unsafe queries are blocked at the graph's guard node; retrieval/reasoning never
  run, and a safe refusal is returned.

## PII protection (`safety/pii.py`)

- **Presidio** (production) or **Regex** (light) backend.
- Entities: PERSON, EMAIL, PHONE, LOCATION/ADDRESS, ORGANIZATION, and Indian
  identifiers **PAN, Aadhaar, Passport**.
- Masking at **three points**:
  1. **ingestion** — before chunks are embedded/stored,
  2. **query** — before the query is embedded/logged,
  3. **output** — final guard before the answer is returned.

## Output safety (`safety/output_safety.py`)

Always-on gate before release, checking:
- **groundedness** — per-sentence support against retrieved context,
- **citation coverage** vs. `SAFETY_MIN_CITATION_COVERAGE`,
- **unsupported claims**,
- **PII leakage** — blocks if `SAFETY_BLOCK_ON_PII_LEAK=true`.

Failing answers are replaced with a safe, non-fabricated fallback and confidence
is capped.

## Secrets & logging

- Secrets use `SecretStr` to avoid accidental logging.
- Never read `os.environ` directly — go through `get_settings()`.
- Logs carry a correlation id but not secrets or raw PII (masked upstream).

## Hardening checklist for production
- Set strong `SUPABASE_JWT_SECRET` / use RS256 JWKS.
- `ENFORCE_TENANT_ISOLATION=true`.
- Switch safety backends to `presidio` / `llama_guard`.
- Move rate limiting to a shared Redis backend.
- Restrict `CORS_ORIGINS` to known frontends.
