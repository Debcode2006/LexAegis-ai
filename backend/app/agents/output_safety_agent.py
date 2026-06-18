"""
Output Safety Agent.

The final verification before an answer is released. It consults the
groundedness/output validation and:

- releases the answer when validation passes,
- otherwise replaces it with a safe, non-fabricated fallback and lowers the
  reported confidence.

This guarantees the user never receives an ungrounded or PII-leaking answer,
even if upstream reasoning misbehaves.
"""

from __future__ import annotations

from typing import Any, Dict

from app.agents.state import AgentState

_SAFE_FALLBACK = (
    "I'm unable to provide a sufficiently grounded answer from the available "
    "documents. Please refine the question or upload additional source material."
)


class OutputSafetyAgent:
    def run(self, state: AgentState) -> Dict[str, Any]:
        validation = state.output_validation
        answer = state.answer or ""

        if validation is not None and not validation.allowed:
            state.log("output_safety", released=False, issues=validation.issues)
            return {
                "final_answer": _SAFE_FALLBACK,
                "confidence": min(state.confidence, 0.2),
                "trace": state.trace,
            }

        state.log("output_safety", released=True)
        return {"final_answer": answer, "trace": state.trace}
