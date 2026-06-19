# Ollama Setup

Ollama serves the local LLMs used for reasoning (Qwen3 / Llama 3.1) and input
safety (LlamaGuard). The system runs **without** Ollama in light mode
(heuristic guard + extractive reasoning); install it to enable full LLM
reasoning.

## 1. Install
- Download from https://ollama.com/download (macOS, Windows, Linux), or:
  ```bash
  curl -fsSL https://ollama.com/install.sh | sh
  ```
- Ollama runs a server at `http://localhost:11434` by default.

## 2. Pull models

```bash
ollama pull qwen3            # primary reasoning model
ollama pull llama3.1         # fallback model
ollama pull llama-guard3     # input safety (optional)
```

Verify:
```bash
ollama list
curl http://localhost:11434/api/tags
```

## 3. Backend `.env`

```
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_PRIMARY_MODEL=qwen3
OLLAMA_FALLBACK_MODEL=llama3.1
OLLAMA_REQUEST_TIMEOUT_SECONDS=120
OLLAMA_TEMPERATURE=0.1
OLLAMA_MAX_TOKENS=1024

# enable LLM stages
USE_LLM_FOR_UNDERSTANDING=true
USE_LLM_FOR_REASONING=true

# enable LlamaGuard input safety (otherwise heuristic)
SAFETY_INPUT_GUARD_BACKEND=llama_guard
SAFETY_LLAMA_GUARD_MODEL=llama-guard3
```

## 4. How LexAegis uses it

- `app/llm/ollama_client.py` — thin HTTP client over `/api/chat`.
- `app/llm/provider.py` — `LLMProvider` calls the **primary** model and, on any
  failure (server down, timeout, error), transparently retries the **fallback**.
- Responses are cached by the semantic cache (namespace `llm`).

## 5. Health check
The Ollama client exposes a `health()` method (GET `/api/tags`). If Ollama is
unreachable, the provider's fallback and the agents' deterministic fallbacks keep
the pipeline functional (lower quality, but never a hard failure).

## 6. Performance tips
- First call to a model loads it into memory (slower); subsequent calls are fast.
- Use GPU builds of Ollama for large models.
- Tune `OLLAMA_MAX_TOKENS` / `OLLAMA_TEMPERATURE` for latency vs. quality.

## Fully-local evaluation judge (optional)
DeepEval can judge with a local Ollama model:
```bash
deepeval set-ollama qwen3
```
RAGAS can be pointed at Ollama via its LangChain wrappers (see
[EVALUATION_GUIDE](EVALUATION_GUIDE.md)).
