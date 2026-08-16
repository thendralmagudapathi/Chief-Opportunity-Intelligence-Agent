"""Native tool implementations (Phase 5).

Every tool declares a Pydantic argument schema, a description, a timeout, a
retry policy, a permission scope, a side-effect class and a per-run call cap.
The registry defined here is the single source of truth; ``app.mcp`` exposes the
same registry over the Model Context Protocol rather than duplicating it.

Tools never import ``app.agents`` — that would allow tool-to-agent recursion.
There is no code-execution tool, and there never will be.
"""

from app.tools.factory import build_tool_executor, build_tool_registry
from app.tools.registry import ToolRegistry
from app.tools.types import SideEffect, ToolOutcome, ToolSpec

__all__ = [
    "SideEffect",
    "ToolOutcome",
    "ToolRegistry",
    "ToolSpec",
    "build_tool_executor",
    "build_tool_registry",
]
