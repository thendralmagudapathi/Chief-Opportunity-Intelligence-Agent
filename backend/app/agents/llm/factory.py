"""Build an LLM provider from settings."""

from __future__ import annotations

from app.agents.llm.protocols import LLMProvider
from app.core.config import Settings
from app.inference.gateway import GatewayLLMProvider, build_provider_chain
from app.inference.semantic_cache import build_semantic_cache


def build_llm_provider(settings: Settings) -> LLMProvider:
    if not settings.inference.gateway_enabled:
        return build_provider_chain(settings)[0]
    cache = build_semantic_cache(
        enabled=settings.inference.semantic_cache_enabled,
        redis_url=settings.redis.url if settings.redis.enabled else None,
        ttl_s=settings.inference.semantic_cache_ttl_s,
    )
    return GatewayLLMProvider(
        settings=settings,
        providers=build_provider_chain(settings),
        cache=cache,
    )
