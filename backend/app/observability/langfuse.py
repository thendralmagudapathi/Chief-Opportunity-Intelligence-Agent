"""Optional Langfuse export."""

from __future__ import annotations

from typing import Any

from app.core.config import Settings
from app.core.logging import get_logger

logger = get_logger(__name__)


def configure_langfuse(settings: Settings) -> None:
    obs = settings.observability
    public_key_secret = obs.langfuse_public_key
    secret_key_secret = obs.langfuse_secret_key
    if not public_key_secret or not secret_key_secret:
        return
    try:
        import os

        public_key = public_key_secret.get_secret_value()
        secret_key = secret_key_secret.get_secret_value()
        os.environ.setdefault("LANGFUSE_PUBLIC_KEY", public_key)
        os.environ.setdefault("LANGFUSE_SECRET_KEY", secret_key)
        os.environ.setdefault("LANGFUSE_HOST", obs.langfuse_host)
        logger.info("langfuse_configured", host=obs.langfuse_host)
    except Exception as exc:
        logger.warning("langfuse_configure_failed", error=str(exc))


def log_trace_event(name: str, *, metadata: dict[str, Any] | None = None) -> None:
    try:
        from langfuse.decorators import langfuse_context

        langfuse_context.update_current_trace(name=name, metadata=metadata or {})
    except Exception:
        return
