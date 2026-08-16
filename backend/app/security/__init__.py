"""Security services.

Implemented now: the trust hierarchy and content isolation (``trust.py``), which
must be in place before any external content is ever fetched, and the SSRF egress
guard (``egress.py``) used by tool-layer HTTP fetches.

Scheduled for Phase 6+: the injection classifier and quarantine pipeline.
See docs/SECURITY_MODEL.md for the full control matrix.
"""

from app.security.egress import SafeHttpClient, validate_url
from app.security.trust import (
    ExternalContent,
    TrustLevel,
    render_external,
    sanitize_external_text,
    scan_for_injection,
)

__all__ = [
    "ExternalContent",
    "SafeHttpClient",
    "TrustLevel",
    "render_external",
    "sanitize_external_text",
    "scan_for_injection",
    "validate_url",
]
