"""Ollama chat completion provider."""

from __future__ import annotations

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from app.agents.llm.protocols import LLMResponse, TaskClass
from app.core.config import ModelSettings
from app.core.errors import DependencyUnavailableError
from app.core.logging import get_logger

logger = get_logger(__name__)


class OllamaLLMProvider:
    def __init__(
        self,
        settings: ModelSettings,
        *,
        extraction_model: str | None = None,
    ) -> None:
        self._settings = settings
        self._base_url = settings.base_url.rstrip("/")
        self._extraction_model = extraction_model

    async def complete(
        self,
        prompt: str,
        *,
        task_class: TaskClass = "standard",
        system: str | None = None,
    ) -> LLMResponse:
        if task_class == "extract" and self._extraction_model:
            model = self._extraction_model
        else:
            model = self._settings.for_task(task_class)
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        return await self._chat(model=model, messages=messages)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=0.5, max=4))
    async def _chat(self, *, model: str, messages: list[dict[str, str]]) -> LLMResponse:
        payload = {"model": model, "messages": messages, "stream": False}
        try:
            async with httpx.AsyncClient(timeout=self._settings.request_timeout_s) as client:
                response = await client.post(f"{self._base_url}/api/chat", json=payload)
                response.raise_for_status()
                body = response.json()
        except httpx.HTTPError as exc:
            logger.warning("ollama_chat_failed", error=str(exc))
            raise DependencyUnavailableError("LLM provider unavailable") from exc

        message = body.get("message", {})
        content = str(message.get("content", ""))
        return LLMResponse(
            content=content,
            model=model,
            input_tokens=int(body.get("prompt_eval_count", 0) or 0),
            output_tokens=int(body.get("eval_count", 0) or 0),
        )
