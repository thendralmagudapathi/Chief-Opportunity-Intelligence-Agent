"""Embedding providers and a content-hash cache."""

from __future__ import annotations

import hashlib
import json
import math
import struct
from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import RagSettings
from app.core.errors import DependencyUnavailableError
from app.core.logging import get_logger
from app.retrieval.protocols import EmbeddingProvider

logger = get_logger(__name__)


def _normalize(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        return vector
    return [value / norm for value in vector]


class FakeEmbeddingProvider:
    """Deterministic embeddings for tests and offline development."""

    def __init__(self, *, model_name: str = "fake-embed", dimension: int = 768) -> None:
        self._model_name = model_name
        self._dimension = dimension

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def dimension(self) -> int:
        return self._dimension

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [_normalize(self._hash_vector(text)) for text in texts]

    def _hash_vector(self, text: str) -> list[float]:
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        values: list[float] = []
        while len(values) < self._dimension:
            for offset in range(0, len(digest), 4):
                chunk = digest[offset : offset + 4]
                if len(chunk) < 4:
                    chunk = chunk.ljust(4, b"\x00")
                values.append(struct.unpack("!i", chunk)[0] / 2_147_483_648)
                if len(values) >= self._dimension:
                    break
            digest = hashlib.sha256(digest).digest()
        return values[: self._dimension]


class OllamaEmbeddingProvider:
    def __init__(
        self,
        *,
        base_url: str,
        model_name: str,
        dimension: int,
        timeout_s: float = 60.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model_name = model_name
        self._dimension = dimension
        self._timeout_s = timeout_s

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def dimension(self) -> int:
        return self._dimension

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=0.5, max=4))
    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        payload = {"model": self._model_name, "input": texts}
        try:
            async with httpx.AsyncClient(timeout=self._timeout_s) as client:
                response = await client.post(f"{self._base_url}/api/embed", json=payload)
                response.raise_for_status()
                body = response.json()
        except httpx.HTTPError as exc:
            logger.warning("ollama_embed_failed", error=str(exc))
            raise DependencyUnavailableError("Embedding provider unavailable") from exc

        embeddings = body.get("embeddings")
        if not isinstance(embeddings, list):
            raise DependencyUnavailableError("Embedding provider returned an invalid payload")
        vectors: list[list[float]] = []
        for item in embeddings:
            if not isinstance(item, list):
                raise DependencyUnavailableError("Embedding provider returned an invalid vector")
            vector = [float(value) for value in item]
            if len(vector) != self._dimension:
                raise DependencyUnavailableError(
                    f"Embedding dimension mismatch: expected {self._dimension}, got {len(vector)}"
                )
            vectors.append(_normalize(vector))
        return vectors


class CachedEmbeddingProvider:
    """Wrap any provider with a Redis or in-process cache keyed by content hash."""

    def __init__(
        self,
        inner: EmbeddingProvider,
        *,
        redis_client: Any | None,
        ttl_s: int,
    ) -> None:
        self._inner = inner
        self._redis = redis_client
        self._ttl_s = ttl_s
        self._memory: dict[str, list[float]] = {}

    @property
    def model_name(self) -> str:
        return self._inner.model_name

    @property
    def dimension(self) -> int:
        return self._inner.dimension

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        keys = [_cache_key(self.model_name, text) for text in texts]
        cached: dict[int, list[float]] = {}
        missing_texts: list[str] = []
        missing_indexes: list[int] = []

        for index, (text, key) in enumerate(zip(texts, keys, strict=True)):
            vector = await self._get_cached(key)
            if vector is not None:
                cached[index] = vector
            else:
                missing_indexes.append(index)
                missing_texts.append(text)

        if missing_texts:
            fresh = await self._inner.embed(missing_texts)
            for idx, vector in zip(missing_indexes, fresh, strict=True):
                cached[idx] = vector
                await self._set_cached(keys[idx], vector)

        return [cached[index] for index in range(len(texts))]

    async def _get_cached(self, key: str) -> list[float] | None:
        if self._redis is not None:
            raw = await self._redis.get(key)
            if raw is not None:
                parsed = json.loads(raw)
                if isinstance(parsed, list):
                    return [float(value) for value in parsed]
            return None
        return self._memory.get(key)

    async def _set_cached(self, key: str, vector: list[float]) -> None:
        payload = json.dumps(vector)
        if self._redis is not None:
            await self._redis.set(key, payload, ex=self._ttl_s)
        else:
            self._memory[key] = vector


def _cache_key(model_name: str, text: str) -> str:
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return f"emb:{model_name}:{digest}"


def build_embedding_provider(
    settings: RagSettings,
    *,
    base_url: str,
    redis_client: Any | None,
    cache_ttl_s: int,
) -> EmbeddingProvider:
    if settings.embedding_provider == "fake":
        inner: EmbeddingProvider = FakeEmbeddingProvider(
            model_name="fake-embed", dimension=settings.embedding_dim
        )
    elif settings.embedding_provider == "ollama":
        inner = OllamaEmbeddingProvider(
            base_url=base_url,
            model_name=settings.embedding_model,
            dimension=settings.embedding_dim,
        )
    else:
        raise ValueError(f"Unsupported embedding provider: {settings.embedding_provider}")

    return CachedEmbeddingProvider(inner, redis_client=redis_client, ttl_s=cache_ttl_s)
