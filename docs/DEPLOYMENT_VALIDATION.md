# Deployment Validation

A checklist to confirm a LexAegis AI deployment is fully working — with the exact
commands for each item. Run top to bottom after `up`. Works for local (Ollama)
and production (Gemini); only the LLM check differs.

Set these once per shell:

```bash
# Local:
export API=http://localhost:8000/api/v1
export WEB=http://localhost:3000
# Production: point at your Railway backend + Vercel frontend instead.
# export API=https://<your-backend>.up.railway.app/api/v1
# export WEB=https://<your-frontend>.vercel.app

# A Supabase access token (JWT) for authenticated routes. Get it from the
# browser devtools (Application → Local Storage) after logging in, or via the
# Supabase client. Then:
export TOKEN="paste-supabase-jwt-here"
```

---

## Checklist

```
□ Frontend running
□ Backend running
□ Chroma running
□ LLM reachable (Ollama locally / Gemini in prod)
□ Auth working
□ Upload working
□ Retrieval working
□ Reranking working
□ Citations working
□ Groundedness working
□ Chat history working
```

---

### □ Frontend running
```bash
curl -fsS -o /dev/null -w "%{http_code}\n" "$WEB"     # expect 200
```
Or open `$WEB` in a browser — the login/chat UI should render.

### □ Backend running
```bash
curl -fsS "$API/health"     # expect {"status":"ok",...}
curl -fsS "$API/ready"      # readiness probe
```
Container view:
```bash
docker compose -f docker-compose.local.yml ps   # all 3 "running"/"healthy"
```

### □ Chroma running
```bash
# Inside the compose network the backend reaches it; from the host (local mode
# publishes 8001):
curl -fsS http://localhost:8001/api/v2/heartbeat    # expect a heartbeat json
# Or check the container health:
docker inspect --format '{{.State.Health.Status}}' lexaegis-chroma
```

### □ LLM reachable
Check the backend startup logs for the health line:
```bash
docker compose -f docker-compose.local.yml logs backend | grep "LLM HEALTH"
```
- **Local (Ollama):** expect `[LLM HEALTH] Ollama reachable at http://host.docker.internal:11434 | reasoning=qwen3 installed=True ...`
- **Production (Gemini):** expect `[LLM HEALTH] Gemini reachable at https://generativelanguage.googleapis.com/v1beta | model=gemini-2.5-flash available=True ...`

Direct provider probes:
```bash
# Ollama (local, host):
curl -fsS http://localhost:11434/api/tags | head -c 200

# Gemini (prod): verify the key works (returns a model list):
curl -fsS "https://generativelanguage.googleapis.com/v1beta/models?key=$GEMINI_API_KEY" | head -c 200
```

### □ Auth working
```bash
# Without a token -> 401:
curl -s -o /dev/null -w "%{http_code}\n" "$API/auth/whoami"            # expect 401
# With a valid token -> 200 + your identity:
curl -fsS -H "Authorization: Bearer $TOKEN" "$API/auth/whoami"
```

### □ Upload working
```bash
curl -fsS -X POST "$API/documents/upload" \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@/path/to/contract.pdf" \
  -F "document_type=contract"
# expect a DocumentSummary JSON with a document id + chunk count
```
List ingested docs:
```bash
curl -fsS -H "Authorization: Bearer $TOKEN" "$API/documents"
```

### □ Retrieval working
Ask a question grounded in the uploaded document:
```bash
curl -fsS -X POST "$API/chat" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query":"What is the termination notice period?","include_trace":true}'
```
In the response `trace`, confirm a `retrieval` step returned chunks (non-empty
`chunks`).

### □ Reranking working
In the same `include_trace` response, the trace shows a rerank stage and the
final chunks are ordered by relevance. Locally this requires
`RETRIEVAL_ENABLE_RERANKER=true` (BGE in prod, lexical fallback in light mode).
```bash
curl -fsS -X POST "$API/chat" -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query":"termination clause","include_trace":true}' \
  | python -c "import sys,json; t=json.load(sys.stdin).get('trace',[]); print([s for s in t if 'rerank' in str(s).lower()])"
```

### □ Citations working
The answer text contains inline source tags like `[S1]`, and the response lists
the cited sources:
```bash
curl -fsS -X POST "$API/chat" -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query":"What governs this agreement?"}' \
  | python -c "import sys,json; r=json.load(sys.stdin); print('answer has [S]:', '[S1]' in r.get('answer','')); print('citations:', r.get('citations'))"
```

### □ Groundedness working
Ask something **not** in the documents — the system should refuse rather than
hallucinate:
```bash
curl -fsS -X POST "$API/chat" -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query":"What is the capital of Mars?"}'
# expect the insufficient-evidence / low-groundedness response, not an invented answer
```

### □ Chat history working
Send two turns and confirm prior context is retained (history is persisted per
user/tenant). In the UI, reload the page — previous messages should still appear.
Via API, list/replay depends on your history endpoint; at minimum confirm the
second answer can reference the first turn's subject.

---

## One-shot smoke test

```bash
set -e
curl -fsS "$API/health" >/dev/null && echo "backend ok"
curl -fsS -o /dev/null -w "frontend %{http_code}\n" "$WEB"
docker compose -f docker-compose.local.yml logs backend | grep -q "LLM HEALTH" && echo "llm health logged"
curl -fsS -H "Authorization: Bearer $TOKEN" "$API/auth/whoami" >/dev/null && echo "auth ok"
echo "ALL BASIC CHECKS PASSED"
```

If any step fails, see the troubleshooting table in
[LLM_PROVIDER_GUIDE.md](LLM_PROVIDER_GUIDE.md).
