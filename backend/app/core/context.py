"""Request-scoped context.

The request id doubles as the trace id for synchronous requests and is the
correlation key between HTTP logs, ``agent_runs`` rows and OTel spans.
"""

from __future__ import annotations

import uuid
from contextvars import ContextVar

_request_id: ContextVar[str] = ContextVar("request_id", default="-")


def new_request_id() -> str:
    return uuid.uuid4().hex[:20]


def set_request_id(value: str) -> None:
    _request_id.set(value)


def get_request_id() -> str:
    return _request_id.get()
