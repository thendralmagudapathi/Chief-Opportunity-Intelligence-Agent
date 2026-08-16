"""Schema constants that are baked into DDL.

``EMBEDDING_DIM`` is part of the physical schema: changing it requires a
migration and a re-embed, so it lives here rather than in runtime settings.
``Settings.rag.embedding_dim`` must agree with it, and startup asserts that.
"""

from __future__ import annotations

EMBEDDING_DIM = 768
"""Dimension of ``nomic-embed-text``, the default local embedding model."""
