"""
Local evaluation runner (no heavy dependencies).

Runs the LexAegis agent workflow over the benchmark and writes a report to
`evaluation/results/latest.json`, which the backend's `/api/v1/evaluation/results`
endpoint and the frontend Evaluation Dashboard consume.

Usage:
    python evaluation/evaluate_local.py
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from _harness import RESULTS_PATH, generate_predictions, load_dataset
from offline_metrics import aggregate, score_record


def main() -> None:
    dataset = load_dataset()
    records = generate_predictions(dataset)

    samples = []
    per_sample_scores = []
    for record in records:
        scores = score_record(record)
        per_sample_scores.append(scores)
        samples.append(
            {
                "question": record["question"],
                "answer": record["answer"],
                "ground_truth": record["ground_truth"],
                "confidence": record["confidence"],
                "intent_expected": record["intent_expected"],
                "intent_predicted": record["intent_predicted"],
                "scores": scores,
            }
        )

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dataset": dataset["name"],
        "evaluator": "offline_lexical",
        "summary": aggregate(per_sample_scores),
        "samples": samples,
    }

    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"Wrote {RESULTS_PATH}")
    print("Summary:")
    for metric, value in report["summary"].items():
        print(f"  {metric:>18}: {value}")


if __name__ == "__main__":
    main()
