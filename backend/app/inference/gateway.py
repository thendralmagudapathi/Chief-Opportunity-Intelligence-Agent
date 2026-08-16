"""Model gateway with fallback routing, caching and cost accounting."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from app.agents.llm.protocols import LLMProvider, LLMResponse, TaskClass
from app.core.config import Settings
from app.core.errors import DependencyUnavailableError
from app.core.logging import get_logger
from app.inference.pricing import estimate_llm_cost
from app.inference.semantic_cache import InMemorySemanticCache, RedisSemanticCache
from app.observability.cost import CostLedger
from app.observability.metrics import registry

logger = get_logger(__name__)


@dataclass
class GatewayLLMProvider:
    """Route LLM calls through cache, primary provider and fallback chain."""

    settings: Settings
    providers: list[LLMProvider]
    cache: InMemorySemanticCache | RedisSemanticCache | None = None
    ledger: CostLedger | None = field(default=None)

    async def complete(
        self,
        prompt: str,
        *,
        task_class: TaskClass = "standard",
        system: str | None = None,
    ) -> LLMResponse:
        inference = self.settings.inference
        model_name = self._resolve_model_name(task_class)
        if self.cache is not None:
            cached = await self.cache.get(
                task_class=task_class,
                model=model_name,
                prompt=_cache_prompt(prompt, system),
            )
            if cached is not None:
                registry.increment("llm_cache_hits")
                return cached

        last_error: Exception | None = None
        for index, provider in enumerate(self.providers):
            try:
                response = await provider.complete(
                    prompt,
                    task_class=task_class,
                    system=system,
                )
                self._record_cost(response)
                if self.cache is not None:
                    await self.cache.set(
                        task_class=task_class,
                        model=model_name,
                        prompt=_cache_prompt(prompt, system),
                        response=response,
                        ttl_s=inference.semantic_cache_ttl_s,
                    )
                if index > 0:
                    registry.increment("llm_fallback_success")
                    logger.warning(
                        "llm_fallback_used",
                        provider_index=index,
                        task_class=task_class,
                    )
                return response
            except Exception as exc:
                last_error = exc
                registry.increment("llm_provider_failures")
                logger.warning(
                    "llm_provider_failed",
                    provider_index=index,
                    task_class=task_class,
                    error=str(exc),
                )
        raise DependencyUnavailableError("All LLM providers failed") from last_error

    def _resolve_model_name(self, task_class: TaskClass) -> str:
        from app.finetuning.registry import active_extraction_model

        if task_class == "extract":
            return active_extraction_model(self.settings)
        return self.settings.models.for_task(task_class)

    def _record_cost(self, response: LLMResponse) -> None:
        cost = estimate_llm_cost(response, self.settings.inference)
        if self.ledger is not None:
            self.ledger.record_llm(
                input_tokens=response.input_tokens,
                output_tokens=response.output_tokens,
                cost_usd=cost,
            )
        registry.observe("gateway_llm_cost_usd", cost)


def _cache_prompt(prompt: str, system: str | None) -> str:
    if system:
        return f"{system}\n---\n{prompt}"
    return prompt


def build_provider_chain(settings: Settings) -> list[LLMProvider]:
    from app.agents.llm.cloud import CloudLLMProvider
    from app.agents.llm.fake import FakeLLMProvider
    from app.agents.llm.ollama import OllamaLLMProvider
    from app.agents.llm.vllm import VLLMProvider
    from app.finetuning.registry import active_extraction_model

    extraction_model = active_extraction_model(settings)
    use_ft = settings.finetuning.enabled
    builders: dict[str, Callable[[], LLMProvider]] = {
        "fake": lambda: FakeLLMProvider(model_name=extraction_model),
        "ollama": lambda: OllamaLLMProvider(
            settings.models,
            extraction_model=extraction_model if use_ft else None,
        ),
        "vllm": lambda: VLLMProvider(
            settings.models,
            extraction_model=extraction_model if use_ft else None,
        ),
        "cloud": lambda: CloudLLMProvider(
            settings.models,
            extraction_model=extraction_model if use_ft else None,
        ),
    }
    chain_names = [
        name.strip() for name in settings.inference.fallback_chain.split(",") if name.strip()
    ]
    if not chain_names:
        chain_names = [settings.models.provider]
    providers: list[LLMProvider] = []
    for name in chain_names:
        builder = builders.get(name)
        if builder is None:
            raise ValueError(f"Unknown provider in fallback chain: {name}")
        providers.append(builder())
    return providers
