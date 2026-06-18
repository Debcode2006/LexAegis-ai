"""
Groundedness Agent.

Validates the generated answer against the retrieved context using the always-on
lexical grounding check from the safety layer. Produces an `OutputValidation`
(groundedness score, citation coverage, unsupported claims, PII-leak flag) that
both the Confidence Agent and the Output Safety Agent consume.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from app.agents.state import AgentState
from app.safety.output_safety import OutputSafetyValidator, get_output_validator


class GroundednessAgent:
    def __init__(self, validator: Optional[OutputSafetyValidator] = None) -> None:
        self._validator = validator or get_output_validator()

    def run(self, state: AgentState) -> Dict[str, Any]:
        chunks = state.retrieval.chunks if state.retrieval else []
        validation = self._validator.validate(state.answer or "", chunks)
        state.log(
            "groundedness",
            groundedness=validation.groundedness,
            coverage=validation.citation_coverage,
            allowed=validation.allowed,
        )
        return {"output_validation": validation, "trace": state.trace}
