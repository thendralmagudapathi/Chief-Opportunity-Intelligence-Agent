"""Tool permission scopes for agent runs."""

from __future__ import annotations

from app.tools.errors import ToolPermissionError

# Scopes referenced in docs/SECURITY_MODEL.md §5.
SCOPE_PROFILE_READ = "profile:read"
SCOPE_DOCUMENT_READ = "document:read"
SCOPE_OPPORTUNITY_READ = "opportunity:read"
SCOPE_OPPORTUNITY_WRITE = "opportunity:write"
SCOPE_APPLICATION_WRITE = "application:write"
SCOPE_WEB_FETCH = "web:fetch"
SCOPE_EXTERNAL_COMMUNICATE = "external:communicate"

DEFAULT_INVESTIGATION_SCOPES: frozenset[str] = frozenset(
    {
        SCOPE_PROFILE_READ,
        SCOPE_DOCUMENT_READ,
        SCOPE_OPPORTUNITY_READ,
        SCOPE_OPPORTUNITY_WRITE,
        SCOPE_APPLICATION_WRITE,
        SCOPE_WEB_FETCH,
    }
)


def require_scope(granted: frozenset[str], required: str) -> None:
    if required not in granted:
        raise ToolPermissionError(f"Missing required scope: {required}")
