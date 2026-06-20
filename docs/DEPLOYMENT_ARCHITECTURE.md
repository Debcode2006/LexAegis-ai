# Deployment Architecture

How LexAegis AI is wired in **local development** vs **production**, and how the
pieces talk to each other. Read this once before you touch Docker, Vercel, or
Railway — everything else references the diagrams here.

The single lever that changes the inference backend is the `LLM_PROVIDER`
environment variable (`ollama` locally, `gemini` in production). **No application
code changes between the two.** See [LLM_PROVIDER_GUIDE.md](LLM_PROVIDER_GUIDE.md).

---

## 1. The five components

| Component  | What it does                                  | Local            | Production            |
|------------|-----------------------------------------------|------------------|-----------------------|
| Frontend   | Next.js UI (chat, upload, auth)               | container :3000  | **Vercel**            |
| Backend    | FastAPI: retrieval + agents + safety          | container :8000  | **Railway** container |
| Chroma     | Vector database (embeddings)                  | container :8001  | **Railway** container + volume |
| LLM        | Reasoning / understanding / guard             | **Ollama (host)**| **Gemini API**        |
| Supabase   | Auth + Postgres (**never containerized**)     | managed cloud    | managed cloud         |

> Supabase is a managed service in **both** environments. We never run it in
> Docker. The app only needs its URL + keys.

---

## 2. Local architecture (MODE A)

Ollama runs on your **host machine**. The three containers run in Docker. The
backend reaches Ollama through Docker's special `host.docker.internal` hostname.

```
                         ┌──────────────────────────────┐
   Browser  ───────────► │  Frontend  (container :3000)  │
                         └───────────────┬──────────────┘
                                         │  HTTP /api/v1
                                         ▼
                         ┌──────────────────────────────┐
                         │  Backend   (container :8000)  │
                         │  FastAPI + LangGraph agents   │
                         └───┬───────────────┬──────────┘
                             │               │
              CHROMA_HOST    │               │  OLLAMA_BASE_URL=
              =chroma:8000   │               │  http://host.docker.internal:11434
                             ▼               ▼
              ┌────────────────────┐   ┌──────────────────────────┐
              │ Chroma (cont :8001)│   │  Ollama  (HOST machine)  │
              │  volume: chroma_   │   │  qwen3 / llama3.1 /       │
              │  data (persistent) │   │  llama-guard3            │
              └────────────────────┘   └──────────────────────────┘

   Auth (both layers) ─────────────►  Supabase (managed cloud, not in Docker)
```

Start it:

```bash
cp .env.example backend/.env       # keep LLM_PROVIDER=ollama; fill Supabase
ollama serve                       # on the host (separate terminal)
docker compose -f docker-compose.local.yml up -d --build
# open http://localhost:3000
```

---

## 3. Production architecture (MODE B)

No Ollama anywhere. The backend calls the **Gemini API** over the internet.
Frontend is on Vercel; backend + Chroma run on Railway with a persistent volume.

```
                         ┌──────────────────────────────┐
   Browser  ───────────► │  Frontend  —  VERCEL          │
                         └───────────────┬──────────────┘
                                         │  HTTPS  NEXT_PUBLIC_API_BASE
                                         ▼
                         ┌──────────────────────────────┐
                         │  Backend  —  RAILWAY          │
                         │  FastAPI + LangGraph agents   │
                         │  LLM_PROVIDER=gemini          │
                         └───┬───────────────┬──────────┘
                             │               │
              CHROMA_HOST    │               │  HTTPS
              =chroma:8000   │               ▼
                             ▼        ┌──────────────────────────┐
              ┌────────────────────┐  │  Gemini API (Google)     │
              │ Chroma — RAILWAY   │  │  gemini-2.5-flash / pro   │
              │  Railway VOLUME    │  └──────────────────────────┘
              │  (persistent)      │
              └────────────────────┘

   Auth (both layers) ─────────────►  Supabase (managed cloud)
```

Self-host the same topology with compose:

```bash
cp deployment/production.env.example deployment/production.env   # fill secrets
docker compose --env-file deployment/production.env \
  -f docker-compose.production.yml up -d --build
```

---

## 4. Request flow (a single chat turn)

Identical in both environments — only the LLM hop differs.

```
1. Browser POST /api/v1/chat            (Supabase JWT in Authorization header)
2. Backend  verifies JWT                (Supabase)
3. Backend  input safety guard          (LlamaGuard3  | Gemini classifier)
4. Backend  query understanding         (heuristic by default)
5. Backend  hybrid retrieval            (Chroma dense + BM25 sparse → RRF)
6. Backend  rerank (BGE) + compress
7. Backend  reasoning                   (Qwen3 via Ollama | Gemini)  ← LLM_PROVIDER
8. Backend  groundedness + citations + output safety
9. Browser  renders grounded answer with [S1] citations
```

Steps 3 and 7 are the only LLM calls; both route through `LLMProvider`, which the
factory binds to Ollama or Gemini at startup.

---

## 5. Networking cheat-sheet (why the URLs differ)

| From → To                | Local value                                 | Why |
|--------------------------|---------------------------------------------|-----|
| Browser → Backend        | `http://localhost:8000/api/v1`              | browser is outside Docker; uses the published host port |
| Backend → Chroma         | `http://chroma:8000`                         | same Docker network; service name resolves |
| Backend → Ollama (local) | `http://host.docker.internal:11434`          | Ollama is on the host, not in Docker |
| Backend → Gemini (prod)  | `https://generativelanguage.googleapis.com` | public API |
| Browser → Backend (prod) | `https://<railway-backend>/api/v1`           | set as `NEXT_PUBLIC_API_BASE` at Vercel build |

> `NEXT_PUBLIC_*` values are **baked at build time** into the frontend bundle.
> Changing them requires a rebuild/redeploy of the frontend.

---

## 6. Persistent storage

Chroma is the only stateful container. Its data lives in a **named Docker volume**
(`chroma_data`) locally and a **Railway volume** in production. See
[DEPLOYMENT_VALIDATION.md](DEPLOYMENT_VALIDATION.md) for verification and the
"Persistent storage" section of [DOCKER_FOR_BEGINNERS.md](DOCKER_FOR_BEGINNERS.md)
for backup/restore commands.

| Where        | Volume                | Mount        | Survives restart | Survives rebuild |
|--------------|-----------------------|--------------|------------------|------------------|
| Local Docker | `chroma_data`         | `/data`      | ✅               | ✅               |
| Railway      | Railway volume        | `/data`      | ✅               | ✅               |

---

See also:
[LLM_PROVIDER_GUIDE.md](LLM_PROVIDER_GUIDE.md) ·
[DOCKER_FOR_BEGINNERS.md](DOCKER_FOR_BEGINNERS.md) ·
[DOCKER_DESKTOP_GUIDE.md](DOCKER_DESKTOP_GUIDE.md) ·
[DEPLOYMENT_VALIDATION.md](DEPLOYMENT_VALIDATION.md)
