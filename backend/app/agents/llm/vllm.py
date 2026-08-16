"""vLLM provider with schema-constrained decoding for extraction."""

from __future__ import annotations

from typing import Any

from app.agents.llm.openai_compat import OpenAICompatProvider
from app.agents.llm.protocols import LLMResponse, TaskClass
from app.core.config import ModelSettings


class VLLMProvider:
    """Production inference via vLLM OpenAI-compatible server."""

    def __init__(
        self,
        settings: ModelSettings,
        *,
        extraction_model: str | None = None,
    ) -> None:
        self._settings = settings
        self._extraction_model = extraction_model
        base_url = settings.base_url.rstrip("/")
        if not base_url.endswith("/v1"):
            base_url = f"{base_url}/v1"
        self._client = OpenAICompatProvider(
            base_url=base_url,
            api_key=settings.api_key.get_secret_value() if settings.api_key else None,
            request_timeout_s=settings.request_timeout_s,
            model_resolver=self._resolve_model,
            provider_name="vllm",
        )

    def _resolve_model(self, task_class: TaskClass) -> str:
        if task_class == "extract" and self._extraction_model:
            return self._extraction_model
        return self._settings.for_task(task_class)

    async def complete(
        self,
        prompt: str,
        *,
        task_class: TaskClass = "standard",
        system: str | None = None,
    ) -> LLMResponse:
        json_schema: dict[str, Any] | None = None
        if task_class == "extract":
            from app.schemas.extraction import OpportunityExtraction

            json_schema = OpportunityExtraction.model_json_schema()
        return await self._client.complete(
            prompt,
            task_class=task_class,
            system=system,
            json_schema=json_schema,
        )
