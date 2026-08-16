"""In-process per-tool rate limiting."""

from __future__ import annotations

import time
from collections import defaultdict, deque
from dataclasses import dataclass, field

from app.tools.errors import ToolRateLimitError


@dataclass
class ToolRateLimiter:
    window_s: float = 60.0
    default_limit: int = 120
    per_tool_limit: dict[str, int] = field(default_factory=dict)
    _events: dict[str, deque[float]] = field(default_factory=lambda: defaultdict(deque))

    def check(self, tool_name: str) -> None:
        limit = self.per_tool_limit.get(tool_name, self.default_limit)
        now = time.monotonic()
        window_start = now - self.window_s
        events = self._events[tool_name]
        while events and events[0] < window_start:
            events.popleft()
        if len(events) >= limit:
            raise ToolRateLimitError(f"Rate limit exceeded for {tool_name}")
        events.append(now)
