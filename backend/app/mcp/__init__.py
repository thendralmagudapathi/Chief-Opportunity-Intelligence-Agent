"""Model Context Protocol server (Phase 5).

A transport adapter over the registry in ``app.tools``. Business logic stays in
services and tools; this package only handles protocol concerns, capability
advertisement and per-session authorisation.
"""

from app.mcp.adapter import (
    call_tool_via_mcp,
    check_mcp_conformance,
    outcome_to_mcp_content,
    registry_to_mcp_tools,
)

__all__ = [
    "call_tool_via_mcp",
    "check_mcp_conformance",
    "outcome_to_mcp_content",
    "registry_to_mcp_tools",
]
