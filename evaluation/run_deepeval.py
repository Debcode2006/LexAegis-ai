"""
DeepEval evaluation.

Scores the live pipeline predictions with DeepEval metrics: Groundedness
(Faithfulness), Hallucination, and Answer Quality (Answer Relevancy).

Requires `deepeval` and a judge model. DeepEval defaults to OpenAI; it also
supports local models via its Ollama integration (`deepeval set-ollama`). If
`deepeval` is not installed, this script prints setup guidance and exits cleanly.

Usage:
    pip install deepeval
    # optional fully-local judge:  deepeval set-ollama qwen3
    python evaluation/run_deepeval.py
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from _harness import RESULTS_PATH, generate_predictions, load_dataset


def main() -> None:
    try:
        from deepeval.metrics import (
            AnswerRelevancyMetric,
            FaithfulnessMetric,
            HallucinationMetric,
        )
        from deepeval.test_case import LLMTestCase
    except ImportError:
        print(
            "DeepEval is not installed. Install with:\n"
            "    pip install deepeval\n"
            "Optionally configure a local judge:  deepeval set-ollama qwen3\n"
            "Falling back: run\n"
            "    python evaluation/evaluate_local.py\n"
            "for offline lexical metrics."
        )
        return

    dataset = load_dataset()
    records = generate_predictions(dataset)

    faithfulness = FaithfulnessMetric(threshold=0.5)
    hallucination = HallucinationMetric(threshold=0.5)
    relevancy = AnswerRelevancyMetric(threshold=0.5)

    rows = []
    for r in records:
        case = LLMTestCase(
            input=r["question"],
            actual_output=r["answer"],
            retrieval_context=r["contexts"],
            context=r["contexts"],
            expected_output=r["ground_truth"],
        )
        faithfulness.measure(case)
        hallucination.measure(case)
        relevancy.measure(case)
        rows.append(
            {
                "question": r["question"],
                "groundedness": round(faithfulness.score or 0.0, 4),
                "hallucination": round(hallucination.score or 0.0, 4),
                "answer_quality": round(relevancy.score or 0.0, 4),
            }
        )

    def avg(key: str) -> float:
        return round(sum(row[key] for row in rows) / len(rows), 4) if rows else 0.0

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dataset": dataset["name"],
        "evaluator": "deepeval",
        "summary": {
            "groundedness": avg("groundedness"),
            "hallucination": avg("hallucination"),
            "answer_quality": avg("answer_quality"),
        },
        "samples": rows,
    }
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("DeepEval summary:", json.dumps(report["summary"], indent=2))


if __name__ == "__main__":
    main()
