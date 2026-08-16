"""Agent execution records.

These three tables *are* the agent trace. Persisting them means the Agent Trace
UI and the agent evaluation dataset both work without depending on an external
tracing SaaS being reachable; OpenTelemetry export is additive.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import (
    AgentRunStatus,
    AgentRunType,
    AgentTaskStatus,
    ToolCallStatus,
    ToolTransport,
    enum_column,
)

if TYPE_CHECKING:
    from app.models.user import User


class AgentRun(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "agent_runs"
    __table_args__ = (Index("ix_agent_runs_user_id_created_at", "user_id", "created_at"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    goal_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("goals.id", ondelete="SET NULL")
    )
    #: Correlates HTTP logs, OTel spans and every child row of this run.
    trace_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)

    run_type: Mapped[AgentRunType] = mapped_column(
        enum_column(AgentRunType, "agent_run_type"), nullable=False
    )
    status: Mapped[AgentRunStatus] = mapped_column(
        enum_column(AgentRunStatus, "agent_run_status"),
        default=AgentRunStatus.PENDING,
        nullable=False,
    )
    objective_text: Mapped[str | None] = mapped_column(Text)
    graph_version: Mapped[str | None] = mapped_column(String(32))
    iterations: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    latency_ms: Mapped[int | None] = mapped_column(Integer)

    input_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(10, 6), default=0, nullable=False)
    budget: Mapped[dict[str, Any]] = mapped_column(default=dict, nullable=False)

    #: True when the run completed with reduced capability (dead source, budget
    #: exhaustion, lexical-only retrieval). Surfaced in the report.
    degraded: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    error: Mapped[str | None] = mapped_column(Text)
    result: Mapped[dict[str, Any] | None] = mapped_column(default=None)

    user: Mapped[User] = relationship(back_populates="agent_runs")
    tasks: Mapped[list[AgentTask]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )
    tool_calls: Mapped[list[ToolCall]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )


class AgentTask(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One agent invocation within a run; ``parent_task_id`` models delegation."""

    __tablename__ = "agent_tasks"
    __table_args__ = (
        Index("ix_agent_tasks_agent_run_id_created_at", "agent_run_id", "created_at"),
    )

    agent_run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False
    )
    parent_task_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("agent_tasks.id", ondelete="CASCADE")
    )

    agent_name: Mapped[str] = mapped_column(String(64), nullable=False)
    capability: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[AgentTaskStatus] = mapped_column(
        enum_column(AgentTaskStatus, "agent_task_status"),
        default=AgentTaskStatus.PENDING,
        nullable=False,
    )
    attempt: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    input: Mapped[dict[str, Any] | None] = mapped_column(default=None)
    output: Mapped[dict[str, Any] | None] = mapped_column(default=None)
    error: Mapped[str | None] = mapped_column(Text)

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(10, 6), default=0, nullable=False)
    model_name: Mapped[str | None] = mapped_column(String(128))
    #: Resolved prompt version, so an evaluation result is attributable.
    prompt_version: Mapped[str | None] = mapped_column(String(64))

    run: Mapped[AgentRun] = relationship(back_populates="tasks")
    tool_calls: Mapped[list[ToolCall]] = relationship(back_populates="task")


class ToolCall(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Every tool invocation, including denied and timed-out ones."""

    __tablename__ = "tool_calls"
    __table_args__ = (Index("ix_tool_calls_agent_run_id_created_at", "agent_run_id", "created_at"),)

    agent_run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False
    )
    agent_task_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("agent_tasks.id", ondelete="CASCADE")
    )

    tool_name: Mapped[str] = mapped_column(String(64), nullable=False)
    transport: Mapped[ToolTransport] = mapped_column(
        enum_column(ToolTransport, "tool_transport"), default=ToolTransport.NATIVE, nullable=False
    )
    status: Mapped[ToolCallStatus] = mapped_column(
        enum_column(ToolCallStatus, "tool_call_status"), nullable=False
    )

    arguments: Mapped[dict[str, Any] | None] = mapped_column(default=None)
    #: Large payloads are truncated; ``result_hash`` keeps them verifiable.
    result: Mapped[dict[str, Any] | None] = mapped_column(default=None)
    result_hash: Mapped[str | None] = mapped_column(String(64))
    error: Mapped[str | None] = mapped_column(Text)

    latency_ms: Mapped[int | None] = mapped_column(Integer)
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(10, 6), default=0, nullable=False)
    cache_hit: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    run: Mapped[AgentRun] = relationship(back_populates="tool_calls")
    task: Mapped[AgentTask | None] = relationship(back_populates="tool_calls")
