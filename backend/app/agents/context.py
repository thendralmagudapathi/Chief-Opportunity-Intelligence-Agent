"""Execution context passed into every agent."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.llm.protocols import LLMProvider
from app.core.config import Settings


@dataclass(slots=True)
class RunContext:
    session: AsyncSession
    settings: Settings
    llm: LLMProvider
    run_id: uuid.UUID
    trace_id: str
    user_id: uuid.UUID
    emit: Callable[[str, dict[str, Any]], None] = field(default=lambda _event, _data: None)
