"""Shared OpenAI-compatible chat completion client."""

from __future__ import annotations

from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from app.agents.llm.protocols import LLMResponse, TaskClass
from app.core.errors import DependencyUnavailableError
from app.core.logging import get_logger

logger = get_logger(__name__)


class OpenAICompatProvider:
    """Chat completions against an OpenAI-compatible endpoint (vLLM, cloud)."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str | None = None,
        request_timeout_s: float = 120.0,
        model_resolver: Any,
        provider_name: str = "openai_compat",
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._request_timeout_s = request_timeout_s
        self._model_resolver = model_resolver
        self._provider_name = provider_name

    async def complete(
        self,
        prompt: str,
        *,
        task_class: TaskClass = "standard",
        system: str | None = None,
        json_schema: dict[str, Any] | None = None,
    ) -> LLMResponse:
        model = self._model_resolver(task_class)
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": 0.1,
        }
        if json_schema is not None:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "structured_output", "schema": json_schema},
            }
        return await self._chat(payload)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=0.5, max=4))
    async def _chat(self, payload: dict[str, Any]) -> LLMResponse:
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        url = f"{self._base_url}/chat/completions"
        try:
            async with httpx.AsyncClient(timeout=self._request_timeout_s) as client:
                response = await client.post(url, headers=headers, json=payload)
                response.raise_for_status()
                body = response.json()
        except httpx.HTTPError as exc:
            logger.warning(
                "openai_compat_chat_failed",
                provider=self._provider_name,
                error=str(exc),
            )
            raise DependencyUnavailableError(f"{self._provider_name} unavailable") from exc

        choice = (body.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        content = str(message.get("content") or "")
        usage = body.get("usage") or {}
        return LLMResponse(
            content=content,
            model=str(body.get("model") or payload["model"]),
            input_tokens=int(usage.get("prompt_tokens") or 0),
            output_tokens=int(usage.get("completion_tokens") or 0),
        )


def pydantic_json_schema(model_type: type[Any]) -> dict[str, Any]:
    schema: dict[str, Any] = model_type.model_json_schema()
    return schema
