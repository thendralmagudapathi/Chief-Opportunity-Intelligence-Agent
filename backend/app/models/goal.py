"""User objectives.

An opportunity has no intrinsic score. Every score is computed against a goal,
which is why this table sits on the critical path of the ranking query.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, ForeignKey, Index, SmallInteger, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import GoalStatus, ObjectiveProfile, enum_column

if TYPE_CHECKING:
    from app.models.opportunity import OpportunityScore
    from app.models.user import User


class Goal(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "goals"
    __table_args__ = (Index("ix_goals_user_id_status_priority", "user_id", "status", "priority"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    objective_profile: Mapped[ObjectiveProfile] = mapped_column(
        enum_column(ObjectiveProfile, "objective_profile"),
        default=ObjectiveProfile.CAREER,
        nullable=False,
    )
    priority: Mapped[int] = mapped_column(SmallInteger, default=3, nullable=False)
    status: Mapped[GoalStatus] = mapped_column(
        enum_column(GoalStatus, "goal_status"), default=GoalStatus.ACTIVE, nullable=False
    )
    deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    desired_outcome: Mapped[str | None] = mapped_column(Text)

    constraints: Mapped[dict[str, Any]] = mapped_column(default=dict, nullable=False)
    acceptable_tradeoffs: Mapped[list[Any]] = mapped_column(default=list, nullable=False)
    #: Replaces the profile's default weight vector when present.
    weights_override: Mapped[dict[str, Any] | None] = mapped_column(default=None)

    user: Mapped[User] = relationship(back_populates="goals")
    scores: Mapped[list[OpportunityScore]] = relationship(
        back_populates="goal", cascade="all, delete-orphan"
    )
