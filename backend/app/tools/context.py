"""Execution context for native tools."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.tools.budget import ToolBudget
from app.tools.permissions import DEFAULT_INVESTIGATION_SCOPES
from app.tools.rate_limit import ToolRateLimiter

if TYPE_CHECKING:
    from app.security.egress import SafeHttpClient


@dataclass(slots=True)
class ToolContext:
    session: AsyncSession
    settings: Settings
    user_id: uuid.UUID
    run_id: uuid.UUID | None = None
    goal_id: uuid.UUID | None = None
    task_id: uuid.UUID | None = None
    granted_scopes: frozenset[str] = field(default_factory=lambda: DEFAULT_INVESTIGATION_SCOPES)
    budget: ToolBudget | None = None
    rate_limiter: ToolRateLimiter = field(default_factory=ToolRateLimiter)
    http: SafeHttpClient | None = None
