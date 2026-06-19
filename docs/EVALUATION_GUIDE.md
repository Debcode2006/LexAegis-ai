# Evaluation Guide

Evaluation lives in `evaluation/`. It runs the **real** LexAegis agent workflow
over a benchmark dataset and scores the outputs. Three runners share one
generation harness so they evaluate identical pipeline outputs.

## Files

| File | Purpose |
|---|---|
| `datasets/legal_benchmark.json` | Sample grounded legal QA (documents + Q/A) |
| `_harness.py` | Loads dataset, ingests docs, runs the workflow → predictions |
| `offline_metrics.py` | Dependency-free lexical metrics |
| `evaluate_local.py` | Offline runner → `results/latest.json` |
| `run_ragas.py` | RAGAS metrics (requires `ragas`) |
| `run_deepeval.py` | DeepEval metrics (requires `deepeval`) |
| `results/latest.json` | Latest report (served to the dashboard) |

The harness forces light backends (hashing embeddings, in-memory store, BM25,
lexical reranker, no LLM), so evaluation runs fully offline with no Ollama,
ChromaDB, or model downloads.

## Run it

```bash
# Offline lexical metrics — always works
python evaluation/evaluate_local.py

# RAGAS (Faithfulness, Answer Relevancy, Context Precision, Context Recall)
pip install ragas datasets
python evaluation/run_ragas.py

# DeepEval (Groundedness, Hallucination, Answer Quality)
pip install deepeval
# optional fully-local judge:  deepeval set-ollama qwen3
python evaluation/run_deepeval.py
```

If `ragas`/`deepeval` aren't installed, those scripts print setup guidance and
exit cleanly (they don't fail the build) — use `evaluate_local.py` meanwhile.

## Metrics

### RAGAS
- **Faithfulness** — is the answer supported by retrieved context?
- **Answer Relevancy** — does the answer address the question?
- **Context Precision** — are retrieved contexts relevant?
- **Context Recall** — was the needed context retrieved?

### DeepEval
- **Groundedness (Faithfulness)** — answer support by context.
- **Hallucination** — fabricated content.
- **Answer Quality (Answer Relevancy)** — relevance/quality.

### Offline (lexical approximations)
`faithfulness`, `answer_relevancy`, `groundedness`, `context_precision`,
`context_recall`, `intent_correct`. Indicative scores for fast iteration; the
canonical numbers come from RAGAS/DeepEval.

## Viewing results

The backend serves the latest report:

```
GET /api/v1/evaluation/results
```

Path configurable via `EVALUATION_RESULTS_PATH` (default
`../evaluation/results/latest.json`, resolved relative to the backend cwd). The
frontend **Evaluation Dashboard** (`/evaluation`) renders the summary tiles and
per-sample results.

## Adding samples
Edit `datasets/legal_benchmark.json`: add to `documents` (with text) and
`samples` (`question`, `ground_truth`, `intent`, `relevant_document_ids`), then
re-run a runner.
