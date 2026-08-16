"""Portable column types.

The one interesting type here is :class:`Vector`. It compiles to a real
``pgvector`` column on PostgreSQL and degrades to JSON elsewhere, which is what
lets the same models and the same Alembic migration run against SQLite in tests
without a database server.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import JSON, Dialect, TypeDecorator
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import TypeEngine

#: ``JSONB`` on PostgreSQL, plain ``JSON`` everywhere else.
JSONColumn = JSON().with_variant(JSONB(), "postgresql")


class Vector(TypeDecorator[list[float]]):
    """Fixed-dimension embedding column.

    PostgreSQL: ``vector(dim)`` from the pgvector extension, indexable with
    IVFFlat/HNSW. Other dialects: a JSON array, adequate for tests and for the
    FAISS/Chroma paths where the vector lives outside the database anyway.
    """

    impl = JSON
    cache_ok = True

    def __init__(self, dim: int) -> None:
        self.dim = dim
        super().__init__()

    def load_dialect_impl(self, dialect: Dialect) -> TypeEngine[Any]:
        if dialect.name == "postgresql":
            from pgvector.sqlalchemy import Vector as PGVector

            return dialect.type_descriptor(PGVector(self.dim))
        return dialect.type_descriptor(JSON())

    def process_bind_param(self, value: list[float] | None, dialect: Dialect) -> list[float] | None:
        if value is not None and len(value) != self.dim:
            raise ValueError(
                f"Embedding dimension mismatch: got {len(value)}, column expects {self.dim}"
            )
        return value
