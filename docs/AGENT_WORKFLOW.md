# Agent Workflow

The reasoning core is a LangGraph `StateGraph` in `app/agents/graph.py` that
threads a single `AgentState` (`app/agents/state.py`) through an input guard plus
eight agents.

## Graph

```
START
  └─ guard ──(blocked)──────────────────────────────► END
       └─(continue)─► query_understanding ─► planner ─► retrieval
                       ─► reasoning ─► citation ─► groundedness
                       ─► confidence ─► output_safety ─► END
```

Two backends share the **same node functions**:
- `langgraph` (production) — a compiled `StateGraph`.
- `sequential` (fallback) — used automatically if LangGraph isn't installed or
  `AGENT_ORCHESTRATOR=sequential`.

Each node is wrapped in a trace span (`agent.<name>`) for per-agent latency.

## The agents

| # | Agent | File | Inputs → Outputs |
|---|---|---|---|
| 0 | Input Guard | `guard.py` | query → masked_query, input_safety, blocked |
| 1 | Query Understanding | `query_understanding.py` | query → intent, legal_task, entities |
| 2 | Planner | `planner.py` | intent → plan (workflow, strategy, tools) |
| 3 | Retrieval | `retrieval_agent.py` | masked_query → RetrievalResult |
| 4 | Legal Reasoning | `reasoning.py` | context → answer (context-only, cited) |
| 5 | Citation | `citation.py` | answer + chunks → structured citations |
| 6 | Groundedness | `groundedness.py` | answer + context → OutputValidation |
| 7 | Confidence | `confidence.py` | all signals → confidence (0–1) + breakdown |
| 8 | Output Safety | `output_safety_agent.py` | validation → final_answer or safe fallback |

### Intents
`contract_review`, `clause_comparison`, `compliance_check`, `policy_lookup`,
`regulation_search`, `legal_risk_analysis`, `document_summary`.

### Reasoning rules
The reasoning prompt forbids unsupported claims and requires inline source tags
(`[S1]`, `[S2]`, …). When the LLM is disabled/unavailable, a deterministic
extractive fallback composes a cited answer from the top chunk, so the pipeline
is always functional and grounded.

### Confidence
A transparent weighted blend (weights in `confidence.py`):

| Signal | Weight |
|---|---|
| retrieval_similarity | 0.20 |
| reranker_score | 0.25 |
| source_agreement | 0.15 |
| citation_coverage | 0.20 |
| groundedness | 0.20 |

The full breakdown is returned so the score is explainable.

### Output safety
If output validation fails (coverage below `SAFETY_MIN_CITATION_COVERAGE`, or PII
leak with `SAFETY_BLOCK_ON_PII_LEAK`), the agent replaces the answer with a safe,
non-fabricated fallback and caps confidence at 0.2.

## Extending

Add a node by writing an agent class with `run(state) -> dict` (partial state
update), registering it in `LegalAgentWorkflow._nodes`, and inserting it into
`_PIPELINE_ORDER` (sequential) and the edge list (LangGraph). Because nodes are
plain callables, unit-test each in isolation (see `tests/test_agents.py`).
