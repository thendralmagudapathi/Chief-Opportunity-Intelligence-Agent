"""Build an LLM provider from settings."""

from __future__ import annotations

from app.agents.llm.fake import FakeLLMProvider
from app.agents.llm.ollama import OllamaLLMProvider
from app.agents.llm.protocols import LLMProvider
from app.core.config import Settings
from app.finetuning.registry import active_extraction_model


def build_llm_provider(settings: Settings) -> LLMProvider:
    extraction_model = active_extraction_model(settings)
    if settings.models.provider == "fake":
        return FakeLLMProvider(model_name=extraction_model)
    if settings.models.provider == "ollama":
        return OllamaLLMProvider(
            settings.models,
            extraction_model=extraction_model if settings.finetuning.enabled else None,
        )
    raise ValueError(f"Unsupported model provider: {settings.models.provider}")
