"""
Query Understanding Agent.

Responsibilities: intent classification, legal-task classification, and entity
extraction. Uses the LLM when enabled (structured JSON output) and always has a
deterministic heuristic fallback so the pipeline never blocks on LLM
availability.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from app.agents.base import extract_json
from app.agents.state import AgentState, Intent
from app.core.config import get_settings
from app.core.logging import get_logger
from app.llm.base import ChatMessage, LLMError, Role
from app.llm.provider import LLMProvider

logger = get_logger(__name__)

# Keyword cues per intent for the heuristic classifier.
_INTENT_KEYWORDS = {
    Intent.CLAUSE_COMPARISON: ["compare", "difference between", "versus", "vs ", "differ"],
    Intent.COMPLIANCE_CHECK: ["comply", "compliance", "gdpr", "hipaa", "regulation requires"],
    Intent.POLICY_LOOKUP: ["policy", "policies", "handbook", "guideline"],
    Intent.REGULATION_SEARCH: ["regulation", "statute", "law", "act ", "section of the"],
    Intent.LEGAL_RISK_ANALYSIS: ["risk", "liability", "exposure", "indemnif", "penalty"],
    Intent.DOCUMENT_SUMMARY: ["summar", "overview", "tl;dr", "key points"],
    Intent.CONTRACT_REVIEW: ["clause", "contract", "agreement", "term", "obligation"],
}

_ENTITY_RE = re.compile(r"\b([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*)\b")
_QUOTED_RE = re.compile(r"[\"“']([^\"”']{3,60})[\"”']")
_CLAUSE_REF_RE = re.compile(r"\b(?:clause|section|article)\s+[0-9IVXLC.]+\b", re.I)


class QueryUnderstandingAgent:
    def __init__(self, provider: Optional[LLMProvider] = None) -> None:
        self._provider = provider
        self._use_llm = get_settings().use_llm_for_understanding and provider is not None

    def run(self, state: AgentState) -> Dict[str, Any]:
        query = state.query_for_retrieval()
        result = None
        if self._use_llm:
            result = self._classify_with_llm(query)
        if result is None:
            result = self._classify_heuristic(query)

        state.log("query_understanding", intent=result["intent"].value)
        return {
            "intent": result["intent"],
            "legal_task": result["legal_task"],
            "entities": result["entities"],
            "trace": state.trace,
        }

    # -- LLM path -------------------------------------------------------------

    def _classify_with_llm(self, query: str) -> Optional[Dict[str, Any]]:
        intents = ", ".join(i.value for i in Intent if i != Intent.UNKNOWN)
        prompt = (
            "You are a legal query classifier. Given a user question, respond ONLY "
            "with a JSON object: {\"intent\": one of [" + intents + "], "
            "\"legal_task\": short string, \"entities\": list of strings}.\n\n"
            f"Question: {query}"
        )
        try:
            response = self._provider.chat(
                [ChatMessage(role=Role.USER, content=prompt)], temperature=0.0, max_tokens=256
            )
        except LLMError as exc:
            logger.warning("Query understanding LLM failed: %s", exc)
            return None

        data = extract_json(response.content)
        if not data:
            return None
        try:
            intent = Intent(str(data.get("intent", "unknown")))
        except ValueError:
            intent = Intent.UNKNOWN
        return {
            "intent": intent,
            "legal_task": data.get("legal_task") or intent.value,
            "entities": [str(e) for e in (data.get("entities") or [])][:10],
        }

    # -- heuristic path -------------------------------------------------------

    def _classify_heuristic(self, query: str) -> Dict[str, Any]:
        lowered = query.lower()
        intent = Intent.UNKNOWN
        for candidate, keywords in _INTENT_KEYWORDS.items():
            if any(k in lowered for k in keywords):
                intent = candidate
                break
        if intent == Intent.UNKNOWN:
            intent = Intent.CONTRACT_REVIEW  # safe default for legal QA

        return {
            "intent": intent,
            "legal_task": intent.value,
            "entities": self._extract_entities(query),
        }

    @staticmethod
    def _extract_entities(query: str) -> List[str]:
        entities: List[str] = []
        entities.extend(m.group(1) for m in _CLAUSE_REF_RE.finditer(query))
        entities.extend(m.group(1) for m in _QUOTED_RE.finditer(query))
        # Proper-noun-ish multi-word capitalized spans (skip sentence-initial only).
        for m in _ENTITY_RE.finditer(query):
            span = m.group(1)
            if " " in span or span.isupper():
                entities.append(span)
        # De-duplicate, preserve order.
        seen = set()
        unique = []
        for e in entities:
            key = e.lower()
            if key not in seen:
                seen.add(key)
                unique.append(e)
        return unique[:10]
