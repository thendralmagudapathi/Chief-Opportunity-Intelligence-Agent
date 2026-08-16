"""Per-run tool call budgets."""

from __future__ import annotations

from dataclasses import dataclass, field

from app.tools.errors import ToolBudgetError


@dataclass
class ToolBudget:
    max_total: int
    remaining_usd: float
    calls_used: int = 0
    per_tool: dict[str, int] = field(default_factory=dict)

    @classmethod
    def from_run_budget(cls, budget: dict[str, object]) -> ToolBudget:
        max_raw = budget.get("max_tool_calls_total", 60)
        remaining_raw = budget.get("remaining_usd", 1.0)
        max_total = int(max_raw) if isinstance(max_raw, (int, float, str)) else 60
        remaining = float(remaining_raw) if isinstance(remaining_raw, (int, float, str)) else 1.0
        return cls(max_total=max_total, remaining_usd=remaining)

    def check_total(self) -> None:
        if self.calls_used >= self.max_total:
            raise ToolBudgetError("Run tool-call budget exhausted")

    def check_tool(self, tool_name: str, max_calls: int) -> None:
        used = self.per_tool.get(tool_name, 0)
        if used >= max_calls:
            raise ToolBudgetError(f"Per-tool budget exhausted for {tool_name}")

    def record(self, *, tool_name: str, cost_usd: float) -> None:
        self.calls_used += 1
        self.per_tool[tool_name] = self.per_tool.get(tool_name, 0) + 1
        self.remaining_usd = max(0.0, self.remaining_usd - cost_usd)
