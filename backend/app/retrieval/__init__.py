"""Retrieval pipeline (Phase 3).

Interfaces to be defined here before any implementation:

* ``EmbeddingProvider``   — ``embed(texts) -> list[Vector]``
* ``VectorStore``         — ``upsert`` / ``search`` / ``delete``, implemented by
  pgvector (default), Qdrant, Chroma and FAISS
* ``Reranker``            — cross-encoder scoring of ``(query, passage)`` pairs
* ``DocumentParser``      — bytes to structured text
* ``Retriever``           — expansion, hybrid fusion, rerank, context filtering

Business logic must depend on these protocols, never on a concrete store.
"""
