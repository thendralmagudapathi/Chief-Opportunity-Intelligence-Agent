"""Semantic-ish LLM response cache backed by Redis."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from app.agents.llm.protocols import LLMResponse, TaskClass
from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class CacheKey:
    task_class: TaskClass
    model: str
    prompt_hash: str


class InMemorySemanticCache:
    """Process-local cache for tests and development."""

    def __init__(self) -> None:
        self._store: dict[str, LLMResponse] = {}

    async def get(self, *, task_class: TaskClass, model: str, prompt: str) -> LLMResponse | None:
        return self._store.get(_cache_key(task_class, model, prompt))

    async def set(
        self,
        *,
        task_class: TaskClass,
        model: str,
        prompt: str,
        response: LLMResponse,
        ttl_s: int,
    ) -> None:
        del ttl_s
        self._store[_cache_key(task_class, model, prompt)] = response


class RedisSemanticCache:
    def __init__(self, *, url: str, prefix: str = "oia:llm:") -> None:
        self._url = url
        self._prefix = prefix

    async def get(self, *, task_class: TaskClass, model: str, prompt: str) -> LLMResponse | None:
        import redis.asyncio as redis

        key = self._prefix + _cache_key(task_class, model, prompt)
        client = redis.from_url(self._url, decode_responses=True)
        try:
            raw = await client.get(key)
        finally:
            await client.aclose()
        if raw is None:
            return None
        payload = json.loads(raw)
        logger.info("semantic_cache_hit", task_class=task_class, model=model)
        return LLMResponse(
            content=str(payload["content"]),
            model=str(payload["model"]),
            input_tokens=int(payload.get("input_tokens") or 0),
            output_tokens=int(payload.get("output_tokens") or 0),
        )

    async def set(
        self,
        *,
        task_class: TaskClass,
        model: str,
        prompt: str,
        response: LLMResponse,
        ttl_s: int,
    ) -> None:
        import redis.asyncio as redis

        key = self._prefix + _cache_key(task_class, model, prompt)
        payload = json.dumps(
            {
                "content": response.content,
                "model": response.model,
                "input_tokens": response.input_tokens,
                "output_tokens": response.output_tokens,
            }
        )
        client = redis.from_url(self._url, decode_responses=True)
        try:
            await client.set(key, payload, ex=ttl_s)
        finally:
            await client.aclose()


def _cache_key(task_class: TaskClass, model: str, prompt: str) -> str:
    digest = hashlib.sha256(f"{task_class}:{model}:{prompt}".encode()).hexdigest()
    return digest


def build_semantic_cache(
    *, enabled: bool, redis_url: str | None, ttl_s: int
) -> InMemorySemanticCache | RedisSemanticCache | None:
    if not enabled:
        return None
    if redis_url:
        return RedisSemanticCache(url=redis_url)
    return InMemorySemanticCache()
