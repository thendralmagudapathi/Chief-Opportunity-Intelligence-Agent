"""Retrieval pipeline (Phase 3).

Interfaces and implementations for document parsing, chunking, embeddings,
vector search, hybrid fusion, reranking and profile retrieval.
"""

from app.retrieval.factory import RetrievalStack, build_retrieval_stack
from app.retrieval.protocols import (
    DocumentParser,
    EmbeddingProvider,
    ObjectStorage,
    ParsedDocument,
    Reranker,
    RetrievalResult,
    ScoredPassage,
    TextChunk,
    VectorStore,
)
from app.retrieval.retriever import ProfileRetriever

__all__ = [
    "DocumentParser",
    "EmbeddingProvider",
    "ObjectStorage",
    "ParsedDocument",
    "ProfileRetriever",
    "Reranker",
    "RetrievalResult",
    "RetrievalStack",
    "ScoredPassage",
    "TextChunk",
    "VectorStore",
    "build_retrieval_stack",
]
