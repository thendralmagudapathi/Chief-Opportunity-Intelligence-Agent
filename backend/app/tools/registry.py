"""Tool registry — single source of truth for native and MCP transports."""

from __future__ import annotations

from typing import Any

from app.tools.base import BaseTool
from app.tools.types import ToolSpec


class ToolRegistry:
    def __init__(self, tools: dict[str, BaseTool]) -> None:
        self._tools = tools

    @classmethod
    def from_instances(cls, instances: list[BaseTool]) -> ToolRegistry:
        tools = {tool.name: tool for tool in instances}
        if len(tools) != len(instances):
            raise ValueError("Duplicate tool names in registry")
        return cls(tools)

    def get(self, name: str) -> BaseTool:
        tool = self._tools.get(name)
        if tool is None:
            raise KeyError(name)
        return tool

    def list_tools(self) -> list[ToolSpec]:
        return [tool.spec() for tool in self._tools.values()]

    def names(self) -> list[str]:
        return sorted(self._tools)

    def tool_descriptions(self) -> dict[str, str]:
        return {name: tool.description for name, tool in self._tools.items()}

    def input_schema(self, name: str) -> dict[str, Any]:
        return self.get(name).spec().input_schema
