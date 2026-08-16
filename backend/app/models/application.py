"""Application lifecycle and realised outcomes.

``outcomes`` is the ground truth for outcome evaluation (docs/EVALUATION_PLAN.md
§8) and the only legitimate label source for a future fine-tuning dataset.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import ApplicationStatus, OutcomeType, enum_column

if TYPE_CHECKING:
    from app.models.opportunity import Opportunity
    from app.models.user import User


class Application(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "applications"
    __table_args__ = (Index("ix_applications_user_id_status", "user_id", "status"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    opportunity_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("opportunities.id", ondelete="CASCADE"), nullable=False
    )

    status: Mapped[ApplicationStatus] = mapped_column(
        enum_column(ApplicationStatus, "application_status"),
        default=ApplicationStatus.DRAFT,
        nullable=False,
    )
    channel: Mapped[str | None] = mapped_column(String(64))
    #: Drafts, checklists and prepared forms produced by the Action Agent.
    artifacts: Mapped[dict[str, Any]] = mapped_column(default=dict, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)

    #: ``submitted`` is only reachable after an explicit human approval.
    approved_by_user_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship(back_populates="applications")
    opportunity: Mapped[Opportunity] = relationship(back_populates="applications")
    outcomes: Mapped[list[Outcome]] = relationship(
        back_populates="application", cascade="all, delete-orphan"
    )


class Outcome(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "outcomes"
    __table_args__ = (Index("ix_outcomes_user_id_outcome", "user_id", "outcome"),)

    #: Nullable: an opportunity can be ignored or expire without an application.
    application_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("applications.id", ondelete="CASCADE")
    )
    opportunity_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("opportunities.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    outcome: Mapped[OutcomeType] = mapped_column(
        enum_column(OutcomeType, "outcome_type"), nullable=False
    )
    occurred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    details: Mapped[dict[str, Any]] = mapped_column(default=dict, nullable=False)

    application: Mapped[Application | None] = relationship(back_populates="outcomes")
