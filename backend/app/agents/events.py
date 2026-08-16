"""In-memory SSE event buffer for active runs."""

from __future__ import annotations

import asyncio
import contextlib
import uuid
from collections import defaultdict
from typing import Any


class InvestigationEventStore:
    def __init__(self) -> None:
        self._events: dict[uuid.UUID, list[dict[str, Any]]] = defaultdict(list)
        self._queues: dict[uuid.UUID, asyncio.Queue[dict[str, Any] | None]] = defaultdict(
            asyncio.Queue
        )
        self._cancelled: set[uuid.UUID] = set()

    def append(self, run_id: uuid.UUID, event: str, data: dict[str, Any]) -> None:
        payload = {"event": event, "data": data}
        self._events[run_id].append(payload)
        queue = self._queues[run_id]
        with contextlib.suppress(asyncio.QueueFull):
            queue.put_nowait(payload)

    def history(self, run_id: uuid.UUID) -> list[dict[str, Any]]:
        return list(self._events.get(run_id, []))

    async def subscribe(self, run_id: uuid.UUID) -> asyncio.Queue[dict[str, Any] | None]:
        queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
        self._queues[run_id] = queue
        for item in self.history(run_id):
            await queue.put(item)
        return queue

    def close(self, run_id: uuid.UUID) -> None:
        queue = self._queues.get(run_id)
        if queue is not None:
            queue.put_nowait(None)

    def cancel(self, run_id: uuid.UUID) -> None:
        self._cancelled.add(run_id)
        self.close(run_id)

    def is_cancelled(self, run_id: uuid.UUID) -> bool:
        return run_id in self._cancelled


event_store = InvestigationEventStore()
