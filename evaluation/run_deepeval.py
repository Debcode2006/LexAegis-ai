"""
DeepEval evaluation.

Scores the live pipeline predictions with DeepEval metrics: Groundedness
(Faithfulness), Hallucination, and Answer Quality (Answer Relevancy).

Judge model: **Gemini Flash 2.5** (matching the production LLM). DeepEval ships a
native `GeminiModel` (backed by the `google-genai` SDK), so no OpenAI key is
needed — the judge reads `GEMINI_API_KEY` / `GEMINI_MODEL` from the environment.
If `deepeval` is not installed or `GEMINI_API_KEY` is unset, the script prints
setup guidance and exits cleanly (falling back to `evaluate_local.py`).

Usage:
    pip install deepeval
    export GEMINI_API_KEY=<your-google-ai-studio-key>   # Windows: $env:GEMINI_API_KEY=...
    export GEMINI_MODEL=gemini-2.5-flash                 # optional, this is the default
    export DEEPEVAL_TELEMETRY_OPT_OUT=YES                # optional, skip telemetry
    python evaluation/run_deepeval.py
"""

from __future__ import annotations

import json
import os
import random
import threading
import time
from datetime import datetime, timezone

from _harness import RESULTS_PATH, generate_predictions, load_dataset

# --- Free-tier survival -----------------------------------------------------
# Gemini's free tier caps gemini-2.5-flash at ~5 requests/minute, AND the model
# intermittently returns 503 UNAVAILABLE ("high demand") regardless of quota.
# Two independent defenses, both env-overridable:
#
#   1. Throttle  — space judge calls >= GEMINI_MIN_INTERVAL_SECONDS apart so we
#      stay under the RPM limit (avoids 429 proactively).
#   2. Retry     — ride out transient errors with exponential backoff. DeepEval's
#      own Gemini retry only classifies 429/4xx-auth as transient; it does NOT
#      retry 503/5xx, so a single overload would otherwise abort the whole run.
#      We retry those ourselves around the judge call.
#
# Load is also capped (DEEPEVAL_MAX_SAMPLES, hallucination metric off by default)
# so the run is short and minimally exposed to transient outages.
GEMINI_MIN_INTERVAL_SECONDS = float(os.environ.get("GEMINI_MIN_INTERVAL_SECONDS", "15"))
GEMINI_MAX_RETRIES = int(os.environ.get("GEMINI_MAX_RETRIES", "8"))
GEMINI_BACKOFF_CAP_SECONDS = float(os.environ.get("GEMINI_BACKOFF_CAP_SECONDS", "75"))
MAX_SAMPLES = int(os.environ.get("DEEPEVAL_MAX_SAMPLES", "3"))  # 0 = all
INCLUDE_HALLUCINATION = os.environ.get(
    "DEEPEVAL_INCLUDE_HALLUCINATION", "false"
).lower() in ("1", "true", "yes")

# HTTP statuses / message markers we treat as transient (retryable).
_RETRYABLE_STATUS = {429, 500, 502, 503, 504}
_RETRYABLE_MARKERS = (
    "503", "500", "502", "504", "unavailable", "resource_exhausted",
    "overloaded", "high demand", "try again",
)


# Per-DAY free-tier quota markers. A daily-quota 429 will NOT recover for hours
# (resets ~midnight Pacific), so retrying it is pointless AND harmful — every
# retry is itself a request that eats the remaining daily budget. Treat it as
# fatal so we fail fast with guidance instead of burning quota in a backoff loop.
_DAILY_QUOTA_MARKERS = ("perday", "per day", "requests per day", "free_tier_requests")


def _is_daily_quota(exc: Exception) -> bool:
    """True for a per-day free-tier quota exhaustion (not recoverable today)."""

    message = str(exc).lower()
    return any(marker in message for marker in _DAILY_QUOTA_MARKERS)


def _is_transient(exc: Exception) -> bool:
    """True for rate-limit / temporary server errors worth retrying.

    Per-day quota exhaustion is explicitly excluded — it cannot recover within
    the run, and retrying it only consumes the remaining daily budget.
    """

    if _is_daily_quota(exc):
        return False
    code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
    if isinstance(code, int) and code in _RETRYABLE_STATUS:
        return True
    message = str(exc).lower()
    return any(marker in message for marker in _RETRYABLE_MARKERS)


def _resilient_call(fn, *, min_interval: float, max_retries: int, backoff_cap: float):
    """Wrap a callable to (1) throttle and (2) retry transient API errors.

    Calls are spaced >= min_interval apart; a transient failure (429/5xx,
    including Gemini's 503 "high demand") is retried with exponential backoff +
    jitter. Non-transient errors propagate immediately.
    """

    lock = threading.Lock()
    last = [0.0]

    def wrapped(*args, **kwargs):
        attempt = 0
        while True:
            with lock:
                wait = min_interval - (time.monotonic() - last[0])
                if wait > 0:
                    time.sleep(wait)
                last[0] = time.monotonic()
            try:
                return fn(*args, **kwargs)
            except Exception as exc:  # noqa: BLE001 - classify, then retry or re-raise
                attempt += 1
                if attempt > max_retries or not _is_transient(exc):
                    raise
                backoff = min(min_interval * (2 ** (attempt - 1)), backoff_cap)
                backoff += random.uniform(0, 3)
                print(
                    f"[retry {attempt}/{max_retries}] transient API error "
                    f"({type(exc).__name__}); backing off {backoff:.0f}s..."
                )
                time.sleep(backoff)

    return wrapped


def main() -> None:
    try:
        from deepeval.metrics import (
            AnswerRelevancyMetric,
            FaithfulnessMetric,
            HallucinationMetric,
        )
        from deepeval.models import GeminiModel
        from deepeval.test_case import LLMTestCase
    except ImportError:
        print(
            "DeepEval is not installed. Install with:\n"
            "    pip install deepeval\n"
            "Falling back: run\n"
            "    python evaluation/evaluate_local.py\n"
            "for offline lexical metrics."
        )
        return

    # Judge = Gemini Flash 2.5 (DeepEval's native GeminiModel uses the google-genai
    # SDK, so no OpenAI key is required). Without a key we cannot judge — bail out
    # cleanly rather than silently falling back to OpenAI / erroring mid-run.
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print(
            "GEMINI_API_KEY is not set — DeepEval needs a judge model.\n"
            "    export GEMINI_API_KEY=<your-google-ai-studio-key>\n"
            "    export GEMINI_MODEL=gemini-2.5-flash   # optional (default)\n"
            "Falling back: run\n"
            "    python evaluation/evaluate_local.py\n"
            "for offline lexical metrics (no judge LLM needed)."
        )
        return

    judge = GeminiModel(
        model=os.environ.get("GEMINI_MODEL", "gemini-2.5-flash"),
        api_key=api_key,
        temperature=0,
    )
    # Throttle + transient-retry every judge call. With async_mode=False below,
    # DeepEval only ever calls the sync `generate`, so wrapping it is sufficient.
    judge.generate = _resilient_call(
        judge.generate,
        min_interval=GEMINI_MIN_INTERVAL_SECONDS,
        max_retries=GEMINI_MAX_RETRIES,
        backoff_cap=GEMINI_BACKOFF_CAP_SECONDS,
    )

    dataset = load_dataset()
    records = generate_predictions(dataset)
    if MAX_SAMPLES > 0:
        records = records[:MAX_SAMPLES]

    # async_mode=False serializes the metric's internal LLM calls so the throttle
    # above actually paces them — concurrent calls would all fire at once and trip
    # the rate limit regardless of spacing. Hallucination is opt-in: it adds an
    # extra judge call per sample and overlaps with Faithfulness, so it is off by
    # default to keep the run short and resilient under free-tier limits.
    faithfulness = FaithfulnessMetric(threshold=0.5, model=judge, async_mode=False)
    relevancy = AnswerRelevancyMetric(threshold=0.5, model=judge, async_mode=False)
    hallucination = (
        HallucinationMetric(threshold=0.5, model=judge, async_mode=False)
        if INCLUDE_HALLUCINATION
        else None
    )

    print(
        f"Running DeepEval over {len(records)} sample(s) | "
        f"metrics: faithfulness, answer_relevancy"
        f"{', hallucination' if hallucination else ''} | "
        f"judge={judge.get_model_name()} | spacing={GEMINI_MIN_INTERVAL_SECONDS:.0f}s"
    )

    rows = []
    for i, r in enumerate(records, 1):
        print(f"  [{i}/{len(records)}] {r['question'][:70]}...")
        case = LLMTestCase(
            input=r["question"],
            actual_output=r["answer"],
            retrieval_context=r["contexts"],
            context=r["contexts"],
            expected_output=r["ground_truth"],
        )
        try:
            faithfulness.measure(case)
            relevancy.measure(case)
            row = {
                "question": r["question"],
                "groundedness": round(faithfulness.score or 0.0, 4),
                "answer_quality": round(relevancy.score or 0.0, 4),
            }
            if hallucination is not None:
                hallucination.measure(case)
                row["hallucination"] = round(hallucination.score or 0.0, 4)
            rows.append(row)
        except Exception as exc:  # noqa: BLE001
            if _is_daily_quota(exc):
                print(
                    "\n=== Gemini free-tier DAILY quota exhausted ===\n"
                    f"The {judge.get_model_name()} free tier allows only ~20 requests/day, "
                    "and that budget is used up for today (resets ~midnight Pacific).\n"
                    "No retry can recover this today. Fastest options:\n"
                    "  1. Judge with a DIFFERENT model (separate daily quota), e.g.:\n"
                    "       GEMINI_MODEL=gemini-2.5-flash-lite python evaluation/run_deepeval.py\n"
                    "       GEMINI_MODEL=gemini-2.0-flash      python evaluation/run_deepeval.py\n"
                    "  2. Enable billing on the API key (removes the 20/day cap).\n"
                    "  3. Wait for the daily reset, then re-run.\n"
                    "  4. Ship a guaranteed-valid report NOW with no judge LLM:\n"
                    "       python evaluation/evaluate_local.py\n"
                )
                return
            raise

    def avg(key: str) -> float:
        values = [row[key] for row in rows if key in row]
        return round(sum(values) / len(values), 4) if values else 0.0

    summary = {
        "groundedness": avg("groundedness"),
        "answer_quality": avg("answer_quality"),
    }
    if hallucination is not None:
        summary["hallucination"] = avg("hallucination")

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dataset": dataset["name"],
        "evaluator": "deepeval",
        "judge_model": judge.get_model_name(),
        "summary": summary,
        "samples": rows,
    }
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("DeepEval summary:", json.dumps(report["summary"], indent=2))


if __name__ == "__main__":
    main()
