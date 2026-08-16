"""Token cost estimation for gateway accounting."""

from __future__ import annotations

from app.agents.llm.protocols import LLMResponse
from app.core.config import InferenceSettings


def estimate_llm_cost(response: LLMResponse, settings: InferenceSettings) -> float:
    input_cost = (response.input_tokens / 1000.0) * settings.input_cost_per_1k
    output_cost = (response.output_tokens / 1000.0) * settings.output_cost_per_1k
    return round(input_cost + output_cost, 6)
