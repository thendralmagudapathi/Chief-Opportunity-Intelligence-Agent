"""Base tool contract."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, ClassVar

from pydantic import BaseModel

from app.tools.context import ToolContext
from app.tools.permissions import require_scope
from app.tools.types import SideEffect, ToolSpec


class BaseTool(ABC):
    name: ClassVar[str]
    description: ClassVar[str]
    args_model: ClassVar[type[BaseModel]]
    permission_scope: ClassVar[str]
    side_effects: ClassVar[SideEffect] = SideEffect.NONE
    timeout_s: ClassVar[float] = 30.0
    max_calls_per_run: ClassVar[int] = 10
    max_retries: ClassVar[int] = 0
    cost_usd: ClassVar[float] = 0.0

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name,
            description=self.description,
            permission_scope=self.permission_scope,
            side_effects=self.side_effects,
            timeout_s=self.timeout_s,
            max_calls_per_run=self.max_calls_per_run,
            max_retries=self.max_retries,
            cost_usd=self.cost_usd,
            input_schema=self.args_model.model_json_schema(),
        )

    def parse_args(self, raw: dict[str, Any]) -> BaseModel:
        return self.args_model.model_validate(raw)

    def check_permission(self, ctx: ToolContext) -> None:
        require_scope(ctx.granted_scopes, self.permission_scope)

    @abstractmethod
    async def run(self, args: BaseModel, ctx: ToolContext) -> dict[str, Any]:
        """Execute the tool and return a JSON-serialisable payload."""
