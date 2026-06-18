# LexAegis AI — Backend (Phase 1)

FastAPI ingress gateway: configuration, structured logging, Supabase JWT auth,
tenant routing, and per-user / per-tenant rate limiting.

> Phases 2–4 (retrieval, LangGraph agents, safety, observability, evaluation,
> frontend, Docker) are layered on top of this foundation.

## Layout

```
backend/
  app/
    main.py                 # App factory + middleware wiring
    core/
      config.py             # Pydantic-Settings (single source of truth)
      logging.py            # Structured logging + request correlation id
      exceptions.py         # Error hierarchy + consistent error envelopes
    auth/
      supabase.py           # Supabase JWT verification (HS256 / RS256)
      models.py             # Principal model
    middleware/
      request_context.py    # X-Request-ID + access logging
      tenant.py             # Tenant resolution
    services/
      rate_limiter.py       # Token-bucket limiter (memory; redis-ready)
    api/
      deps.py               # DI: auth, tenant, rate-limit guards
      router.py             # Router aggregator
      v1/routes/            # health, auth
  tests/                    # config, auth, rate-limit, health tests
  requirements.txt          # full stack (all phases)
  requirements-phase1.txt   # minimal Phase 1 + test deps
```

## Setup

```bash
# from repo root
python -m venv .venv
# Windows:  .venv\Scripts\activate     |  *nix: source .venv/bin/activate
pip install -r backend/requirements-phase1.txt

cp .env.example backend/.env   # then edit SUPABASE_JWT_SECRET etc.
```

## Run

```bash
# *nix
bash scripts/run_backend.sh
# Windows PowerShell
powershell -File scripts/run_backend.ps1
# or directly
cd backend && uvicorn app.main:app --reload
```

Open http://localhost:8000/docs

## Smoke test

```bash
curl http://localhost:8000/api/v1/health
# auth (needs a Supabase HS256 token signed with SUPABASE_JWT_SECRET):
curl -H "Authorization: Bearer <token>" http://localhost:8000/api/v1/auth/whoami
```

## Tests

```bash
cd backend
pip install pytest pytest-asyncio
pytest
```

The test suite mints HS256 tokens with a local secret, so no live Supabase
project is needed to validate the auth + rate-limit + tenant pipeline.
