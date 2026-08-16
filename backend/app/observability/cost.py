"""Cost accounting helpers."""

from __future__ import annotations

from dataclasses import dataclass, field

from app.observability.metrics import registry


@dataclass
class CostLedger:
    llm_input_tokens: int = 0
    llm_output_tokens: int = 0
    tool_cost_usd: float = 0.0
    llm_cost_usd: float = 0.0

    @property
    def total_usd(self) -> float:
        return self.tool_cost_usd + self.llm_cost_usd

    def record_llm(self, *, input_tokens: int, output_tokens: int, cost_usd: float) -> None:
        self.llm_input_tokens += input_tokens
        self.llm_output_tokens += output_tokens
        self.llm_cost_usd += cost_usd
        registry.increment("llm_calls")
        registry.observe("llm_cost_usd", cost_usd)

    def record_tool(self, *, cost_usd: float) -> None:
        self.tool_cost_usd += cost_usd
        registry.increment("tool_calls")
        registry.observe("tool_cost_usd", cost_usd)

    def emit(self) -> None:
        registry.observe("investigation_cost_usd", self.total_usd)


@dataclass
class InvestigationCostTracker:
    ledgers: dict[str, CostLedger] = field(default_factory=dict)

    def for_run(self, run_id: str) -> CostLedger:
        return self.ledgers.setdefault(run_id, CostLedger())
