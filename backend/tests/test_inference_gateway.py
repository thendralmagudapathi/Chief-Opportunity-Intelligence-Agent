"""Model gateway and semantic cache tests."""

from __future__ import annotations

import pytest
from app.agents.llm.fake import FakeLLMProvider
from app.agents.llm.protocols import LLMResponse, TaskClass
from app.core.errors import DependencyUnavailableError
from app.inference.gateway import GatewayLLMProvider
from app.inference.pricing import estimate_llm_cost
from app.inference.semantic_cache import InMemorySemanticCache


class _FailingProvider:
    async def complete(
        self,
        prompt: str,
        *,
        task_class: TaskClass = "standard",
        system: str | None = None,
    ):
        del prompt, task_class, system
        raise DependencyUnavailableError("primary down")


async def test_gateway_falls_back_to_secondary_provider(settings) -> None:  # type: ignore[no-untyped-def]
    gateway = GatewayLLMProvider(
        settings=settings,
        providers=[_FailingProvider(), FakeLLMProvider()],
    )
    response = await gateway.complete("understand the objective", task_class="standard")
    assert response.content


async def test_semantic_cache_returns_cached_response(settings) -> None:  # type: ignore[no-untyped-def]
    settings.inference.semantic_cache_enabled = True
    cache = InMemorySemanticCache()
    gateway = GatewayLLMProvider(
        settings=settings,
        providers=[FakeLLMProvider()],
        cache=cache,
    )
    first = await gateway.complete("Which ML frameworks?", task_class="extract")
    second = await gateway.complete("Which ML frameworks?", task_class="extract")
    assert first.content == second.content


def test_estimate_llm_cost(settings) -> None:  # type: ignore[no-untyped-def]
    settings.inference.input_cost_per_1k = 0.1
    settings.inference.output_cost_per_1k = 0.2
    cost = estimate_llm_cost(
        LLMResponse(content="{}", model="fake", input_tokens=1000, output_tokens=500),
        settings.inference,
    )
    assert cost == pytest.approx(0.2)
