# LLM Provider Guide

The LexAegis backend talks to its language model through **one abstraction**, so
the inference backend is switchable with a single environment variable and **no
application code changes**.

```
                    ┌──────────────────────────┐
   agents/safety ──►│      LLMProvider         │   (primary + fallback + cache)
                    └────────────┬─────────────┘
                                 │  app.llm.factory  (reads LLM_PROVIDER)
                 ┌───────────────┴────────────────┐
                 ▼                                 ▼
        ┌─────────────────┐               ┌─────────────────┐
        │  OllamaClient    │               │  GeminiClient    │
        │  (local dev)     │               │  (production)    │
        └─────────────────┘               └─────────────────┘
```

Both clients implement the same `LLMClient` contract (`app/llm/base.py`) and
return the same normalized `LLMResponse`. Callers never import a concrete client.

---

## 1. Ollama provider (local development)

- **When:** `LLM_PROVIDER=ollama` (the default).
- **Models:** `qwen3` (reasoning primary), `llama3.1` (fallback), `llama-guard3`
  (input safety).
- **Transport:** HTTP to a local Ollama server (`OLLAMA_BASE_URL`), httpx only.
- **Health/validation:** startup probes `/api/tags`, checks the required models
  are installed, and sets the process-wide availability flag. If Ollama is down,
  LLM stages auto-disable and the app degrades to heuristic understanding +
  extractive reasoning (no per-request timeout waits).

Key env vars:
```
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_PRIMARY_MODEL=qwen3
OLLAMA_FALLBACK_MODEL=llama3.1
OLLAMA_REQUEST_TIMEOUT_SECONDS=15
OLLAMA_REASONING_TIMEOUT_SECONDS=90
SAFETY_LLAMA_GUARD_MODEL=llama-guard3
```

Pull the models once:
```bash
ollama pull qwen3
ollama pull llama3.1
ollama pull llama-guard3
```

## 2. Gemini provider (production)

- **When:** `LLM_PROVIDER=gemini`.
- **Models:** `gemini-2.5-flash` (recommended default) or `gemini-2.5-pro`.
- **Transport:** the Generative Language REST API
  (`:generateContent`) over httpx — **no extra dependency** is required.
- **Capabilities:** reasoning, query understanding, and a prompt-based input
  safety classifier. Gemini also applies its own built-in safety to every call.
- **Health/validation:** startup checks `GEMINI_API_KEY` is present, probes
  `/models`, and confirms the configured model is listed. Same graceful
  degradation as Ollama if unreachable.

Key env vars:
```
LLM_PROVIDER=gemini
GEMINI_API_KEY=...            # https://aistudio.google.com/apikey
GEMINI_MODEL=gemini-2.5-flash # or gemini-2.5-pro
GEMINI_FALLBACK_MODEL=gemini-2.5-flash
GEMINI_REQUEST_TIMEOUT_SECONDS=30
GEMINI_REASONING_TIMEOUT_SECONDS=90
```

## 3. Provider switching

Switching is **one line**:

```
# local
LLM_PROVIDER=ollama

# production
LLM_PROVIDER=gemini
```

What happens internally when you change it:
1. `app.llm.factory.active_provider()` reads `LLM_PROVIDER`.
2. `create_client(role)` builds an `OllamaClient` or `GeminiClient` for each role
   (`primary`, `fallback`, `guard`).
3. `LLMProvider`, the agents, and the safety guard consume those clients through
   the unchanged `LLMClient` interface.
4. The startup health check dispatches to the matching probe.

No imports, prompts, or agent code change. The message format (`ChatMessage` with
system/user/assistant roles) and response format (`LLMResponse`) are identical
across providers; `GeminiClient` maps system→`systemInstruction` and
assistant→`model` internally.

## 4. Local setup

```bash
cp .env.example backend/.env       # LLM_PROVIDER=ollama (default)
# fill SUPABASE_* values
ollama serve                        # separate terminal
ollama pull qwen3 && ollama pull llama3.1 && ollama pull llama-guard3
docker compose -f docker-compose.local.yml up -d --build
# verify per docs/DEPLOYMENT_VALIDATION.md
```

## 5. Production setup

```bash
cp deployment/production.env.example deployment/production.env
# set GEMINI_API_KEY, SUPABASE_*, CORS_ORIGINS, NEXT_PUBLIC_*
docker compose --env-file deployment/production.env \
  -f docker-compose.production.yml up -d --build
```
(For managed hosting, use Vercel + Railway — sections F and G below.)

## 6. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `[LLM HEALTH] Ollama UNREACHABLE` | Ollama not running / wrong URL | `ollama serve`; in Docker use `OLLAMA_BASE_URL=http://host.docker.internal:11434` |
| `Reasoning model 'qwen3' is NOT installed` | model not pulled | `ollama pull qwen3` |
| `LLM_PROVIDER=gemini but GEMINI_API_KEY is empty` | missing key | set `GEMINI_API_KEY` |
| `[LLM HEALTH] Gemini API UNREACHABLE` | bad key / no network / wrong model | test the key with the `/models?key=` curl in DEPLOYMENT_VALIDATION |
| Answers are always extractive (no LLM) | LLM auto-disabled at startup | check the health log; fix reachability or set `USE_LLM_FOR_REASONING=true` |
| `Unknown LLM_PROVIDER` warning | typo | use exactly `ollama` or `gemini` |
| Gemini answers truncated | `GEMINI_MAX_TOKENS` too low | raise it |
| 401 on every request | JWT not configured | set `SUPABASE_JWT_SECRET` |

---

# Appendix — Complete deployment reference

## A. All files created

**Backend (provider layer)**
- `backend/app/llm/gemini_client.py` — Gemini REST client (`LLMClient`).
- `backend/app/llm/factory.py` — provider selection + per-role client factory.

**Config / env**
- `deployment/production.env.example` — production backend env (Gemini).

**Docker**
- `backend/Dockerfile`, `backend/.dockerignore`, `backend/docker-entrypoint.sh`
- `frontend/Dockerfile`, `frontend/.dockerignore`, `frontend/public/.gitkeep`
- `docker-compose.local.yml`, `docker-compose.production.yml`

**Docs**
- `docs/DEPLOYMENT_ARCHITECTURE.md`
- `docs/DEPLOYMENT_VALIDATION.md`
- `docs/LLM_PROVIDER_GUIDE.md` (this file)

## B. All files modified

- `backend/app/core/config.py` — added `llm_provider`, `GeminiSettings`
  (incl. `GEMINI_MODEL` alias), wired into `Settings`.
- `backend/app/llm/provider.py` — `LLMProvider` now builds clients via the
  factory (provider-agnostic) instead of hardcoding Ollama.
- `backend/app/llm/runtime.py` — docstring generalized to "active LLM backend".
- `backend/app/safety/input_safety.py` — `LlamaGuardGuard` → provider-aware
  `ModelGuard` (alias kept); guard client built by the factory.
- `backend/app/core/startup.py` — provider-aware health check
  (`_check_ollama` / `_check_gemini`) + Gemini startup warnings.
- `backend/requirements.txt` — note that Gemini needs no new dependency.
- `.env.example` — `LLM_PROVIDER` selector + Gemini block.
- `frontend/next.config.mjs` — `output: "standalone"` for the Docker image.
- `backend/tests/test_llm.py` — Gemini mapping + parsing tests.

## C. Docker startup sequence

1. `docker compose ... build` — builds backend + frontend images (Chroma is
   pulled).
2. `chroma` starts → becomes **healthy** (heartbeat).
3. `backend` starts (waits for Chroma health) → entrypoint prints the active
   provider → Uvicorn boots → lifespan runs `run_startup_checks()` +
   `run_llm_health_check()`.
4. `frontend` starts (after backend) → serves the standalone Next.js server.
5. Each container's `HEALTHCHECK` flips it to **healthy**.

## D. Local development workflow

```bash
# one-time
cp .env.example backend/.env            # LLM_PROVIDER=ollama
ollama pull qwen3 llama3.1 llama-guard3

# each session
ollama serve
docker compose -f docker-compose.local.yml up -d --build
docker compose -f docker-compose.local.yml logs -f backend   # watch LLM HEALTH
# code changes:
docker compose -f docker-compose.local.yml up -d --build backend
# stop (keeps Chroma data):
docker compose -f docker-compose.local.yml down
```

## E. Production deployment workflow (self-hosted compose)

```bash
cp deployment/production.env.example deployment/production.env
# fill: GEMINI_API_KEY, SUPABASE_*, CORS_ORIGINS, NEXT_PUBLIC_*
docker compose --env-file deployment/production.env \
  -f docker-compose.production.yml up -d --build
# validate per docs/DEPLOYMENT_VALIDATION.md (set API/WEB to your hosts)
```

## F. Vercel deployment workflow (frontend)

Assumes you have a GitHub repo and a free Vercel account.

1. Push the repo to GitHub.
2. <https://vercel.com> → **Add New… → Project** → import the repo.
3. **Root Directory:** set to `frontend`.
4. **Framework Preset:** Next.js (auto-detected).
5. **Environment Variables** (Project Settings → Environment Variables):
   - `NEXT_PUBLIC_API_BASE = https://<your-railway-backend>/api/v1`
   - `NEXT_PUBLIC_SUPABASE_URL = https://<project>.supabase.co`
   - `NEXT_PUBLIC_SUPABASE_ANON_KEY = <anon key>`
   > These are inlined at build time. After changing any of them, **Redeploy**.
6. **Deploy.** Vercel builds and gives you `https://<app>.vercel.app`.
7. Copy that URL into the backend's `CORS_ORIGINS` on Railway (section G), then
   redeploy the backend so the browser isn't blocked by CORS.

> You do **not** need the frontend Dockerfile for Vercel — Vercel builds Next.js
> natively. The Dockerfile is for local/self-hosted compose.

## G. Railway deployment workflow (backend + Chroma)

Assumes a free Railway account and the repo on GitHub.

**Backend service**
1. <https://railway.app> → **New Project → Deploy from GitHub repo**.
2. Railway creates a service. In **Settings → Build**, set the **Root Directory**
   to `backend` (it will use `backend/Dockerfile` automatically).
3. **Variables** tab — paste everything from `deployment/production.env`:
   - `LLM_PROVIDER=gemini`, `GEMINI_API_KEY=...`, `GEMINI_MODEL=gemini-2.5-flash`
   - `SUPABASE_*`
   - `CORS_ORIGINS=https://<your-app>.vercel.app`
   - `ENVIRONMENT=production`, `LOG_JSON=true`
   - `RETRIEVAL_VECTOR_STORE=chroma`, `CHROMA_USE_HTTP_CLIENT=true`,
     `CHROMA_HOST=<chroma-service>`, `CHROMA_PORT=8000`
4. **Networking → Generate Domain** → this public URL is your `API` base; put
   `<domain>/api/v1` into Vercel's `NEXT_PUBLIC_API_BASE`.

**Chroma service**
5. In the same project → **New → Docker Image** → `chromadb/chroma:1.0.0`.
6. **Variables:** `IS_PERSISTENT=TRUE`, `ANONYMIZED_TELEMETRY=FALSE`.
7. **Volumes:** add a volume mounted at **`/data`** — this is the persistent,
   restart-and-rebuild-surviving store (see DEPLOYMENT_ARCHITECTURE §6).
8. Note the Chroma service's **private** network name and set the backend's
   `CHROMA_HOST` to it (Railway services talk over the private network).

> **Does Railway need the GPU PyTorch packages?** **No.** Railway runs the
> backend on CPU; there is no GPU. The backend image installs **CPU-only torch**
> (see `backend/Dockerfile`), so embeddings/reranker run on CPU and none of the
> `nvidia_*_cu13` CUDA packages are installed. The Gemini provider itself needs no
> torch at all — it's a REST call. The CPU image is smaller and builds faster,
> which also keeps you within Railway's build limits.

**Wire-up order**
9. Deploy Chroma → deploy Backend (set `CHROMA_HOST`) → set Vercel
   `NEXT_PUBLIC_API_BASE` to the backend domain and redeploy frontend → add the
   Vercel domain to backend `CORS_ORIGINS` and redeploy backend.
10. Validate end-to-end with `docs/DEPLOYMENT_VALIDATION.md`.

---

No deployment step is left undocumented. Start at
[DEPLOYMENT_ARCHITECTURE.md](DEPLOYMENT_ARCHITECTURE.md) for the big picture, then
[DEPLOYMENT_VALIDATION.md](DEPLOYMENT_VALIDATION.md) to verify your deployment.
