"""MCP transport adapter over the native tool registry."""

from __future__ import annotations

import json
from typing import Any

from app.tools.executor import ToolExecutor
from app.tools.registry import ToolRegistry
from app.tools.types import ToolOutcome


def registry_to_mcp_tools(registry: ToolRegistry) -> list[Any]:
    """Convert registry specs to MCP Tool objects."""
    from mcp.types import Tool as MCPTool

    return [
        MCPTool(
            name=spec.name,
            description=spec.description,
            inputSchema=spec.input_schema,
        )
        for spec in registry.list_tools()
    ]


def outcome_to_mcp_content(outcome: ToolOutcome) -> list[Any]:
    from mcp.types import TextContent

    payload = outcome.model_dump(mode="json")
    return [TextContent(type="text", text=json.dumps(payload, indent=2))]


async def call_tool_via_mcp(
    registry: ToolRegistry,
    executor: ToolExecutor,
    *,
    name: str,
    arguments: dict[str, Any],
    ctx: Any,
) -> list[Any]:
    from app.models.enums import ToolTransport

    outcome = await executor.invoke(
        name,
        arguments,
        ctx,
        transport=ToolTransport.MCP,
    )
    return outcome_to_mcp_content(outcome)


def check_mcp_conformance(registry: ToolRegistry) -> None:
    """Validate registry exports are MCP-compatible."""
    tools = registry_to_mcp_tools(registry)
    if len(tools) != 15:
        raise AssertionError(f"Expected 15 tools, found {len(tools)}")
    names = {tool.name for tool in tools}
    if len(names) != len(tools):
        raise AssertionError("Duplicate MCP tool names")
    for tool in tools:
        if not tool.description:
            raise AssertionError(f"Tool {tool.name} missing description")
        schema = tool.input_schema
        if not isinstance(schema, dict) or schema.get("type") != "object":
            raise AssertionError(f"Tool {tool.name} has invalid input schema")
