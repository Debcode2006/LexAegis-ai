"""
RAGAS evaluation.

Computes the canonical RAGAS metrics (Faithfulness, Answer Relevancy, Context
Precision, Context Recall) over the live pipeline predictions.

Requires `ragas` and an LLM/embeddings judge configured for RAGAS (by default
RAGAS uses OpenAI; point it at a local Ollama model via RAGAS's LangChain
integration if you prefer fully-local judging). If `ragas` is not installed, this
script prints setup guidance and exits without failing the build.

Usage:
    pip install ragas datasets
    python evaluation/run_ragas.py
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from _harness import RESULTS_PATH, generate_predictions, load_dataset


def main() -> None:
    try:
        from datasets import Dataset
        from ragas import evaluate
        from ragas.metrics import (
            answer_relevancy,
            context_precision,
            context_recall,
            faithfulness,
        )
    except ImportError:
        print(
            "RAGAS is not installed. Install with:\n"
            "    pip install ragas datasets\n"
            "Then configure a judge LLM (OpenAI key or a local Ollama model via\n"
            "ragas's LangChain wrappers) and re-run. Falling back: run\n"
            "    python evaluation/evaluate_local.py\n"
            "for offline lexical metrics."
        )
        return

    dataset = load_dataset()
    records = generate_predictions(dataset)

    hf = Dataset.from_dict(
        {
            "question": [r["question"] for r in records],
            "answer": [r["answer"] for r in records],
            "contexts": [r["contexts"] for r in records],
            "ground_truth": [r["ground_truth"] for r in records],
        }
    )

    result = evaluate(
        hf,
        metrics=[faithfulness, answer_relevancy, context_precision, context_recall],
    )
    summary = {k: round(float(v), 4) for k, v in result.items()}

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dataset": dataset["name"],
        "evaluator": "ragas",
        "summary": summary,
        "samples": [],
    }
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("RAGAS summary:", json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
