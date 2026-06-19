"""
Offline (dependency-free) evaluation metrics.

Lexical approximations of the RAGAS/DeepEval metrics so the benchmark always runs
locally with zero heavy dependencies. These are *indicative* scores for fast
iteration; the canonical, model-based scores come from `run_ragas.py` /
`run_deepeval.py`.

- faithfulness / groundedness : answer-token support by the retrieved contexts.
- answer_relevancy            : answer overlap with the question + ground truth.
- context_precision           : fraction of retrieved docs that are relevant.
- context_recall              : fraction of relevant docs that were retrieved.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_STOP = {
    "the", "a", "an", "of", "to", "and", "or", "for", "in", "on", "is", "are",
    "be", "shall", "any", "this", "that", "by", "with", "as", "it", "its",
}


def _tokens(text: str) -> set:
    return {t for t in _TOKEN_RE.findall(text.lower()) if t not in _STOP}


def _overlap(a: str, b: str) -> float:
    ta, tb = _tokens(a), _tokens(b)
    if not ta:
        return 0.0
    return len(ta & tb) / len(ta)


def score_record(record: Dict[str, Any]) -> Dict[str, float]:
    answer = record["answer"]
    contexts = record.get("contexts", [])
    context_blob = "\n".join(contexts)

    faithfulness = _overlap(answer, context_blob)
    answer_relevancy = _overlap(
        answer, record["question"] + " " + record["ground_truth"]
    )

    relevant = set(record.get("relevant_document_ids", []))
    retrieved = list(record.get("retrieved_document_ids", []))
    retrieved_set = set(retrieved)
    context_precision = (
        len(relevant & retrieved_set) / len(retrieved_set) if retrieved_set else 0.0
    )
    context_recall = len(relevant & retrieved_set) / len(relevant) if relevant else 0.0

    return {
        "faithfulness": round(faithfulness, 4),
        "answer_relevancy": round(answer_relevancy, 4),
        "groundedness": round(faithfulness, 4),
        "context_precision": round(context_precision, 4),
        "context_recall": round(context_recall, 4),
        "intent_correct": float(record.get("intent_expected") == record.get("intent_predicted")),
    }


def aggregate(per_sample: List[Dict[str, float]]) -> Dict[str, float]:
    if not per_sample:
        return {}
    keys = per_sample[0].keys()
    return {k: round(sum(s[k] for s in per_sample) / len(per_sample), 4) for k in keys}
