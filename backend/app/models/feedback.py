"""User feedback signals.

Stored raw and never used to auto-tune anything. Promotion into an evaluation or
training dataset is an explicit, reviewed step (brief §36).
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import ForeignKey, Index, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import FeedbackSignal, enum_column

if TYPE_CHECKING:
    from app.models.opportunity import Opportunity
    from app.models.user import User


class Feedback(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "feedback"
    __table_args__ = (Index("ix_feedback_user_id_created_at", "user_id", "created_at"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    opportunity_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("opportunities.id", ondelete="CASCADE")
    )
    agent_run_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("agent_runs.id", ondelete="SET NULL")
    )

    signal: Mapped[FeedbackSignal] = mapped_column(
        enum_column(FeedbackSignal, "feedback_signal"), nullable=False
    )
    comment: Mapped[str | None] = mapped_column(Text)
    payload: Mapped[dict[str, Any]] = mapped_column(default=dict, nullable=False)

    user: Mapped[User] = relationship(back_populates="feedback")
    opportunity: Mapped[Opportunity | None] = relationship(back_populates="feedback")
