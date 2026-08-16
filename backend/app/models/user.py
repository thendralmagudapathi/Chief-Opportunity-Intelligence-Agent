"""User account and structured profile."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Numeric, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.agent_run import AgentRun
    from app.models.application import Application
    from app.models.document import Document
    from app.models.feedback import Feedback
    from app.models.goal import Goal
    from app.models.memory import MemoryRecord


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str | None] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_superuser: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    profile: Mapped[UserProfile | None] = relationship(
        back_populates="user", cascade="all, delete-orphan", uselist=False, lazy="selectin"
    )
    goals: Mapped[list[Goal]] = relationship(
        back_populates="user", cascade="all, delete-orphan", lazy="selectin"
    )
    documents: Mapped[list[Document]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    agent_runs: Mapped[list[AgentRun]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    applications: Mapped[list[Application]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    feedback: Mapped[list[Feedback]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    memories: Mapped[list[MemoryRecord]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class UserProfile(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """The structured half of the personal knowledge base.

    Free-form sections are JSON documents validated by Pydantic on write rather
    than by DDL, because their shape evolves faster than the schema. The
    unstructured half lives in :class:`~app.models.document.Document`.
    """

    __tablename__ = "user_profiles"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False
    )

    headline: Mapped[str | None] = mapped_column(String(255))
    summary: Mapped[str | None] = mapped_column(Text)
    location_country: Mapped[str | None] = mapped_column(String(2))  # ISO-3166-1 alpha-2
    location_city: Mapped[str | None] = mapped_column(String(120))
    timezone: Mapped[str | None] = mapped_column(String(64))
    years_experience: Mapped[Decimal | None] = mapped_column(Numeric(4, 1))

    salary_expectation_min: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    salary_expectation_max: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    salary_currency: Mapped[str | None] = mapped_column(String(3))  # ISO-4217

    skills: Mapped[list[Any]] = mapped_column(default=list, nullable=False)
    work_authorization: Mapped[list[Any]] = mapped_column(default=list, nullable=False)
    education: Mapped[list[Any]] = mapped_column(default=list, nullable=False)
    certifications: Mapped[list[Any]] = mapped_column(default=list, nullable=False)
    languages: Mapped[list[Any]] = mapped_column(default=list, nullable=False)
    interests: Mapped[list[Any]] = mapped_column(default=list, nullable=False)
    preferences: Mapped[dict[str, Any]] = mapped_column(default=dict, nullable=False)
    constraints: Mapped[dict[str, Any]] = mapped_column(default=dict, nullable=False)

    user: Mapped[User] = relationship(back_populates="profile")
