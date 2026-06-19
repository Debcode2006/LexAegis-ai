"""
Legal agent workflow.

Wires the eight agents into a single graph:

    guard (input safety + PII mask)
      └─(blocked)─────────────────────────────► END
      └─(continue)─► query_understanding ─► planner ─► retrieval
                       ─► reasoning ─► citation ─► groundedness
                       ─► confidence ─► output_safety ─► END

Two execution backends share the *same* node functions:
- `langgraph` : production — a compiled `StateGraph`.
- `sequential`: dependency-light fallback (used automatically if LangGraph is
  not installed, or when `AGENT_ORCHESTRATOR=sequential`).

Because every node is a plain `agent.run(state) -> dict` callable, the two
backends are behaviourally identical and each agent is unit-testable in
isolation.
"""

from __future__ import annotations

from typing import Callable, Dict, List, Optional, Tuple

from app.agents.citation import CitationAgent
from app.agents.confidence import ConfidenceAgent
from app.agents.groundedness import GroundednessAgent
from app.agents.guard import InputGuardAgent
from app.agents.output_safety_agent import OutputSafetyAgent
from app.agents.planner import PlannerAgent
from app.agents.query_understanding import QueryUnderstandingAgent
from app.agents.reasoning import LegalReasoningAgent
from app.agents.retrieval_agent import RetrievalAgent
from app.agents.state import AgentState
from app.core.config import get_settings
from app.core.logging import get_logger
from app.llm.provider import LLMProvider
from app.observability.tracing import span
from app.retrieval.pipeline import HybridRetriever

logger = get_logger(__name__)

Node = Callable[[AgentState], Dict]

# Linear node order after the guard.
_PIPELINE_ORDER = [
    "query_understanding",
    "planner",
    "retrieval",
    "reasoning",
    "citation",
    "groundedness",
    "confidence",
    "output_safety",
]


class LegalAgentWorkflow:
    def __init__(
        self,
        *,
        provider: Optional[LLMProvider] = None,
        retriever: Optional[HybridRetriever] = None,
    ) -> None:
        raw_nodes: Dict[str, Node] = {
            "guard": InputGuardAgent().run,
            "query_understanding": QueryUnderstandingAgent(provider=provider).run,
            "planner": PlannerAgent().run,
            "retrieval": RetrievalAgent(retriever=retriever).run,
            "reasoning": LegalReasoningAgent(provider=provider).run,
            "citation": CitationAgent().run,
            "groundedness": GroundednessAgent().run,
            "confidence": ConfidenceAgent().run,
            "output_safety": OutputSafetyAgent().run,
        }
        # Wrap every node in a trace span so per-agent latency is observable.
        self._nodes: Dict[str, Node] = {
            name: self._traced(name, fn) for name, fn in raw_nodes.items()
        }
        self._orchestrator = get_settings().agent_orchestrator.lower()
        self._compiled = None

    @staticmethod
    def _traced(name: str, fn: Node) -> Node:
        def wrapper(state: AgentState) -> Dict:
            with span(f"agent.{name}", {"tenant_id": state.tenant_id}):
                return fn(state)

        return wrapper

    # -- public API -----------------------------------------------------------

    def run(self, query: str, tenant_id: str) -> AgentState:
        state = AgentState(query=query, tenant_id=tenant_id)
        if self._orchestrator == "langgraph":
            compiled = self._build_langgraph()
            if compiled is not None:
                return self._run_langgraph(compiled, state)
        return self._run_sequential(state)

    # -- sequential backend ---------------------------------------------------

    def _run_sequential(self, state: AgentState) -> AgentState:
        state = self._apply(state, self._nodes["guard"](state))
        if state.blocked:
            return state
        for name in _PIPELINE_ORDER:
            state = self._apply(state, self._nodes[name](state))
        return state

    @staticmethod
    def _apply(state: AgentState, updates: Dict) -> AgentState:
        for key, value in updates.items():
            setattr(state, key, value)
        return state

    # -- langgraph backend ----------------------------------------------------

    def _build_langgraph(self):
        if self._compiled is not None:
            return self._compiled
        try:
            from langgraph.graph import END, START, StateGraph
        except ImportError:
            logger.info("LangGraph not installed; using sequential orchestrator.")
            return None

        graph = StateGraph(AgentState)
        for name, fn in self._nodes.items():
            graph.add_node(name, fn)

        graph.add_edge(START, "guard")
        graph.add_conditional_edges(
            "guard",
            lambda s: "blocked" if s.blocked else "continue",
            {"blocked": END, "continue": "query_understanding"},
        )
        for current, nxt in zip(_PIPELINE_ORDER, _PIPELINE_ORDER[1:]):
            graph.add_edge(current, nxt)
        graph.add_edge(_PIPELINE_ORDER[-1], END)

        self._compiled = graph.compile()
        return self._compiled

    @staticmethod
    def _run_langgraph(compiled, state: AgentState) -> AgentState:
        result = compiled.invoke(state)
        if isinstance(result, AgentState):
            return result
        return AgentState.model_validate(result)


_workflow: Optional[LegalAgentWorkflow] = None


def get_workflow() -> LegalAgentWorkflow:
    global _workflow
    if _workflow is None:
        _workflow = LegalAgentWorkflow()
    return _workflow
