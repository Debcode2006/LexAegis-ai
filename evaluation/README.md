# Evaluation

Runs the **live** LexAegis agent workflow over a benchmark dataset and scores the
outputs. See [docs/EVALUATION_GUIDE.md](../docs/EVALUATION_GUIDE.md) for full
detail.

## Quick run (offline, no heavy deps)

```bash
# from the repo root, with the backend venv active
python evaluation/evaluate_local.py
# → writes evaluation/results/latest.json
```

## RAGAS / DeepEval

```bash
pip install ragas datasets   && python evaluation/run_ragas.py
pip install deepeval         && python evaluation/run_deepeval.py
```

If those packages aren't installed, the scripts print setup guidance and exit
cleanly — use `evaluate_local.py` in the meantime.

## Files
- `datasets/legal_benchmark.json` — documents + grounded Q/A.
- `_harness.py` — shared generation (ingest + run workflow → predictions).
- `offline_metrics.py` — dependency-free lexical metrics.
- `evaluate_local.py` / `run_ragas.py` / `run_deepeval.py` — runners.
- `results/latest.json` — latest report (served at `/api/v1/evaluation/results`).

The harness forces light, offline backends, so evaluation needs no Ollama,
ChromaDB, or model downloads.
