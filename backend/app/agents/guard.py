"""
Input Guard node (graph entry).

Implements Layer-2 input safety at the front of the workflow:

- query-time PII masking (so PII never reaches retrieval, the LLM, or logs),
- input safety classification (prompt injection / jailbreak / unsafe request).

If the query is unsafe the node sets `blocked` and a safe refusal as the final
answer, and the graph routes straight to the end.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from app.agents.state import AgentState
from app.core.config import get_settings
from app.safety.input_safety import InputSafetyGuard, get_input_guard
from app.safety.pii import PIIDetector, get_pii_detector, mask_text

_REFUSAL = (
    "This request was blocked by the input safety policy and cannot be processed."
)


class InputGuardAgent:
    def __init__(
        self,
        guard: Optional[InputSafetyGuard] = None,
        detector: Optional[PIIDetector] = None,
    ) -> None:
        cfg = get_settings().safety
        self._enabled = cfg.enable_input_safety
        self._mask_enabled = cfg.enable_pii_masking
        self._guard = guard or get_input_guard()
        self._detector = detector or get_pii_detector()

    def run(self, state: AgentState) -> Dict[str, Any]:
        masked_query = state.query
        if self._mask_enabled:
            masked_query = mask_text(state.query, self._detector).masked_text

        if self._enabled:
            verdict = self._guard.check(masked_query)
            if not verdict.safe:
                state.log("input_guard", blocked=True, categories=verdict.categories)
                return {
                    "masked_query": masked_query,
                    "input_safety": verdict,
                    "blocked": True,
                    "block_reason": ", ".join(verdict.categories) or "unsafe_request",
                    "final_answer": _REFUSAL,
                    "trace": state.trace,
                }
        else:
            verdict = None

        state.log("input_guard", blocked=False)
        return {
            "masked_query": masked_query,
            "input_safety": verdict,
            "blocked": False,
            "trace": state.trace,
        }
