"""Build an LLM provider from settings."""

from __future__ import annotations

from app.agents.llm.fake import FakeLLMProvider
from app.agents.llm.ollama import OllamaLLMProvider
from app.agents.llm.protocols import LLMProvider
from app.core.config import Settings


def build_llm_provider(settings: Settings) -> LLMProvider:
    if settings.models.provider == "fake":
        return FakeLLMProvider()
    if settings.models.provider == "ollama":
        return OllamaLLMProvider(settings.models)
    raise ValueError(f"Unsupported model provider: {settings.models.provider}")
