"""Security services.

Implemented now: the trust hierarchy and content isolation (``trust.py``), which
must be in place before any external content is ever fetched.

Scheduled for Phase 5, when the tool layer lands: the injection classifier and
quarantine pipeline, the SSRF egress guard, and tool permission enforcement.
See docs/SECURITY_MODEL.md for the full control matrix.
"""

from app.security.trust import (
    ExternalContent,
    TrustLevel,
    render_external,
    sanitize_external_text,
    scan_for_injection,
)

__all__ = [
    "ExternalContent",
    "TrustLevel",
    "render_external",
    "sanitize_external_text",
    "scan_for_injection",
]
