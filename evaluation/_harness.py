"""
Shared evaluation harness.

Loads the benchmark dataset, ingests its documents into a light, fully-local
retrieval pipeline (hashing embeddings + in-memory store + BM25 + lexical
reranker), runs the real LexAegis agent workflow over each question, and returns
prediction records (question, answer, contexts, ground_truth).

This is the single generation path reused by `evaluate_local.py`, `run_ragas.py`,
and `run_deepeval.py`, so all three evaluate the *same* live pipeline outputs and
require no Ollama, ChromaDB, or model downloads.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

# Make the backend package importable when running these scripts directly.
_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "backend"))

# Force light, offline backends regardless of the developer's .env.
os.environ.setdefault("EMBEDDING_BACKEND", "hashing")
os.environ.setdefault("EMBEDDING_DIMENSION", "256")
os.environ.setdefault("RETRIEVAL_VECTOR_STORE", "memory")
os.environ.setdefault("RETRIEVAL_RERANKER_BACKEND", "lexical")
os.environ.setdefault("SAFETY_PII_BACKEND", "regex")
os.environ.setdefault("SAFETY_INPUT_GUARD_BACKEND", "heuristic")

from app.agents.graph import LegalAgentWorkflow  # noqa: E402
from app.ingestion.chunking import LegalChunker  # noqa: E402
from app.ingestion.models import DocumentType, PageText, RawDocument  # noqa: E402
from app.retrieval.embeddings import HashingEmbedder  # noqa: E402
from app.retrieval.pipeline import HybridRetriever  # noqa: E402
from app.retrieval.reranker import LexicalReranker  # noqa: E402
from app.retrieval.sparse import BM25Index  # noqa: E402
from app.retrieval.vector_store import InMemoryVectorStore  # noqa: E402

DATASET_PATH = _ROOT / "evaluation" / "datasets" / "legal_benchmark.json"
RESULTS_PATH = _ROOT / "evaluation" / "results" / "latest.json"


def load_dataset(path: Path = DATASET_PATH) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def build_workflow(dataset: Dict[str, Any]) -> LegalAgentWorkflow:
    retriever = HybridRetriever(
        embedder=HashingEmbedder(dimension=256),
        vector_store=InMemoryVectorStore(),
        bm25=BM25Index(),
        reranker=LexicalReranker(),
    )
    chunker = LegalChunker()
    tenant = dataset.get("tenant_id", "benchmark")
    for doc in dataset["documents"]:
        raw = RawDocument(
            document_id=doc["document_id"],
            document_name=doc["document_name"],
            tenant_id=tenant,
            document_type=DocumentType(doc.get("document_type", "unknown")),
            pages=[PageText(page_number=1, text=doc["text"])],
        )
        retriever.index_chunks(chunker.chunk_document(raw))
    return LegalAgentWorkflow(provider=None, retriever=retriever)


def generate_predictions(dataset: Dict[str, Any]) -> List[Dict[str, Any]]:
    workflow = build_workflow(dataset)
    tenant = dataset.get("tenant_id", "benchmark")
    records: List[Dict[str, Any]] = []
    for sample in dataset["samples"]:
        state = workflow.run(sample["question"], tenant_id=tenant)
        contexts = [c.chunk.text for c in (state.retrieval.chunks if state.retrieval else [])]
        retrieved_doc_ids = [
            c.chunk.metadata.document_id for c in (state.retrieval.chunks if state.retrieval else [])
        ]
        records.append(
            {
                "question": sample["question"],
                "answer": state.final_answer or state.answer or "",
                "contexts": contexts,
                "ground_truth": sample["ground_truth"],
                "intent_expected": sample.get("intent"),
                "intent_predicted": state.intent.value,
                "confidence": state.confidence,
                "relevant_document_ids": sample.get("relevant_document_ids", []),
                "retrieved_document_ids": retrieved_doc_ids,
            }
        )
    return records
