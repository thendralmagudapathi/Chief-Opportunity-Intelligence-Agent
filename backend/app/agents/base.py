"""Base agent class."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Generic, TypeVar

from pydantic import BaseModel

from app.agents.card import AgentCard
from app.agents.context import RunContext

InputT = TypeVar("InputT", bound=BaseModel)
OutputT = TypeVar("OutputT", bound=BaseModel)


class BaseAgent(ABC, Generic[InputT, OutputT]):
    card: AgentCard

    @abstractmethod
    async def run(self, payload: InputT, ctx: RunContext) -> OutputT: ...
