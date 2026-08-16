"""The opportunity domain: sources, opportunities, scores, evidence and events.

Design note: ``opportunities`` holds only *objective* facts about an
opportunity. Everything subjective — fit, value, recommendation — lives in
``opportunity_scores``, keyed by the goal it was evaluated against. The same
posting therefore carries different scores under different objectives without
the underlying record ever being rewritten.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, utcnow
from app.db.constants import EMBEDDING_DIM
from app.db.types import Vector
from app.models.enums import (
    ClaimType,
    CompensationPeriod,
    EvidenceStance,
    ObjectiveProfile,
    OpportunityCategory,
    OpportunityEventType,
    OpportunityStatus,
    Recommendation,
    RemoteStatus,
    SourceType,
    enum_column,
)

if TYPE_CHECKING:
    from app.models.application import Application
    from app.models.feedback import Feedback
    from app.models.goal import Goal

#: Normalised dimensions live in [0, 1]; ``overall_score`` is a 0-100 display value.
SCORE_PRECISION = Numeric(6, 4)


class OpportunitySource(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A configured discovery source.

    Sources are rows rather than code constants so enabling, throttling or
    disabling a source is an operational action, not a deploy.
    """

    __tablename__ = "opportunity_sources"

    key: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_type: Mapped[SourceType] = mapped_column(
        enum_column(SourceType, "source_type"), nullable=False
    )
    base_url: Mapped[str | None] = mapped_column(String(1024))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    requires_auth: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    rate_limit_per_minute: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    robots_respected: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    config: Mapped[dict[str, Any]] = mapped_column(default=dict, nullable=False)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)

    opportunities: Mapped[list[Opportunity]] = relationship(back_populates="source")


class Opportunity(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "opportunities"
    __table_args__ = (
        UniqueConstraint("source_id", "external_id", name="uq_opportunities_source_id_external_id"),
        Index("ix_opportunities_category_status", "category", "status"),
        Index("ix_opportunities_organization_domain_title", "organization_domain", "title"),
        Index("ix_opportunities_deadline", "deadline"),
        Index("ix_opportunities_discovered_at", "discovered_at"),
        Index("ix_opportunities_canonical_url", "canonical_url"),
    )

    source_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("opportunity_sources.id", ondelete="SET NULL")
    )
    external_id: Mapped[str | None] = mapped_column(String(255))

    title: Mapped[str] = mapped_column(String(512), nullable=False)
    category: Mapped[OpportunityCategory] = mapped_column(
        enum_column(OpportunityCategory, "opportunity_category"), nullable=False
    )
    subcategory: Mapped[str | None] = mapped_column(String(120))
    organization_name: Mapped[str | None] = mapped_column(String(255))
    organization_domain: Mapped[str | None] = mapped_column(String(255))

    description: Mapped[str | None] = mapped_column(Text)
    summary: Mapped[str | None] = mapped_column(Text)
    language: Mapped[str | None] = mapped_column(String(8))
    #: Untrusted source payload, retained verbatim for re-parsing and audit.
    raw: Mapped[dict[str, Any] | None] = mapped_column(default=None)

    location_country: Mapped[str | None] = mapped_column(String(2))
    location_city: Mapped[str | None] = mapped_column(String(120))
    remote_status: Mapped[RemoteStatus] = mapped_column(
        enum_column(RemoteStatus, "remote_status"), default=RemoteStatus.UNKNOWN, nullable=False
    )

    compensation_min: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    compensation_max: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    compensation_currency: Mapped[str | None] = mapped_column(String(3))
    compensation_period: Mapped[CompensationPeriod | None] = mapped_column(
        enum_column(CompensationPeriod, "compensation_period")
    )

    requirements: Mapped[list[Any]] = mapped_column(default=list, nullable=False)
    eligibility: Mapped[dict[str, Any]] = mapped_column(default=dict, nullable=False)
    required_skills: Mapped[list[Any]] = mapped_column(default=list, nullable=False)
    preferred_skills: Mapped[list[Any]] = mapped_column(default=list, nullable=False)

    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    discovered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    freshness_score: Mapped[float | None] = mapped_column(Float)

    source_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    canonical_url: Mapped[str | None] = mapped_column(String(2048))
    #: sha256 of the normalised text — the cheap exact-duplicate short-circuit.
    content_hash: Mapped[str | None] = mapped_column(String(64), unique=True)
    #: Locality-sensitive hash for near-duplicate probing before embeddings exist.
    simhash: Mapped[int | None] = mapped_column(BigInteger)

    status: Mapped[OpportunityStatus] = mapped_column(
        enum_column(OpportunityStatus, "opportunity_status"),
        default=OpportunityStatus.DISCOVERED,
        nullable=False,
    )
    duplicate_of_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("opportunities.id", ondelete="SET NULL")
    )

    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM))
    embedding_model: Mapped[str | None] = mapped_column(String(128))

    source: Mapped[OpportunitySource | None] = relationship(back_populates="opportunities")
    scores: Mapped[list[OpportunityScore]] = relationship(
        back_populates="opportunity", cascade="all, delete-orphan"
    )
    evidence: Mapped[list[OpportunityEvidence]] = relationship(
        back_populates="opportunity", cascade="all, delete-orphan"
    )
    events: Mapped[list[OpportunityEvent]] = relationship(
        back_populates="opportunity", cascade="all, delete-orphan"
    )
    applications: Mapped[list[Application]] = relationship(back_populates="opportunity")
    feedback: Mapped[list[Feedback]] = relationship(back_populates="opportunity")


class OpportunityScore(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One evaluation of one opportunity against one objective.

    Rows are append-only: re-scoring inserts a new ``weights_version`` /
    ``computed_at`` row so a change in ranking can always be explained after the
    fact by diffing two rows.
    """

    __tablename__ = "opportunity_scores"
    __table_args__ = (
        UniqueConstraint(
            "opportunity_id",
            "goal_id",
            "weights_version",
            name="uq_opportunity_scores_opportunity_id_goal_id_weights_version",
        ),
        Index("ix_opportunity_scores_goal_id_overall_score", "goal_id", "overall_score"),
    )

    opportunity_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("opportunities.id", ondelete="CASCADE"), nullable=False
    )
    goal_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("goals.id", ondelete="CASCADE")
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE")
    )
    agent_run_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("agent_runs.id", ondelete="SET NULL")
    )

    scoring_profile: Mapped[ObjectiveProfile] = mapped_column(
        enum_column(ObjectiveProfile, "scoring_profile"), nullable=False
    )
    weights_version: Mapped[str] = mapped_column(String(64), nullable=False)
    engine_version: Mapped[str] = mapped_column(String(32), nullable=False)

    fit_score: Mapped[Decimal | None] = mapped_column(SCORE_PRECISION)
    value_score: Mapped[Decimal | None] = mapped_column(SCORE_PRECISION)
    probability_of_success: Mapped[Decimal | None] = mapped_column(SCORE_PRECISION)
    strategic_value: Mapped[Decimal | None] = mapped_column(SCORE_PRECISION)
    time_sensitivity: Mapped[Decimal | None] = mapped_column(SCORE_PRECISION)
    effort_score: Mapped[Decimal | None] = mapped_column(SCORE_PRECISION)
    risk_score: Mapped[Decimal | None] = mapped_column(SCORE_PRECISION)
    learning_value: Mapped[Decimal | None] = mapped_column(SCORE_PRECISION)
    network_value: Mapped[Decimal | None] = mapped_column(SCORE_PRECISION)
    long_term_value: Mapped[Decimal | None] = mapped_column(SCORE_PRECISION)

    overall_score: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False)
    confidence: Mapped[Decimal | None] = mapped_column(SCORE_PRECISION)
    recommendation: Mapped[Recommendation | None] = mapped_column(
        enum_column(Recommendation, "recommendation")
    )

    #: Structured, evidence-backed factors the agents produced. The engine
    #: consumes these; the score can be recomputed offline from them alone.
    factors: Mapped[dict[str, Any]] = mapped_column(default=dict, nullable=False)
    #: WHY THIS / WHY NOW / WHY ME / WHAT COULD GO WRONG payload.
    explanation: Mapped[dict[str, Any]] = mapped_column(default=dict, nullable=False)
    computed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    opportunity: Mapped[Opportunity] = relationship(back_populates="scores")
    goal: Mapped[Goal | None] = relationship(back_populates="scores")


class OpportunityEvidence(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A single claim with provenance.

    No high-severity risk and no recommendation may reference a claim without a
    row here; the decision service enforces that, not a prompt.
    """

    __tablename__ = "opportunity_evidence"
    __table_args__ = (
        Index("ix_opportunity_evidence_opportunity_id_stance", "opportunity_id", "stance"),
    )

    opportunity_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("opportunities.id", ondelete="CASCADE"), nullable=False
    )
    agent_run_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("agent_runs.id", ondelete="SET NULL")
    )
    agent_name: Mapped[str | None] = mapped_column(String(64))

    claim: Mapped[str] = mapped_column(Text, nullable=False)
    claim_type: Mapped[ClaimType] = mapped_column(
        enum_column(ClaimType, "claim_type"), default=ClaimType.UNKNOWN, nullable=False
    )
    stance: Mapped[EvidenceStance] = mapped_column(
        enum_column(EvidenceStance, "evidence_stance"),
        default=EvidenceStance.NEUTRAL,
        nullable=False,
    )
    value: Mapped[dict[str, Any] | None] = mapped_column(default=None)

    source_url: Mapped[str | None] = mapped_column(String(2048))
    source_title: Mapped[str | None] = mapped_column(String(512))
    source_trust: Mapped[str | None] = mapped_column(String(32))
    retrieved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    confidence: Mapped[Decimal | None] = mapped_column(SCORE_PRECISION)

    opportunity: Mapped[Opportunity] = relationship(back_populates="evidence")


class OpportunityEvent(UUIDPrimaryKeyMixin, Base):
    """Append-only lifecycle log; source of the "new since last check" view."""

    __tablename__ = "opportunity_events"
    __table_args__ = (
        Index("ix_opportunity_events_opportunity_id_created_at", "opportunity_id", "created_at"),
    )

    opportunity_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("opportunities.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE")
    )
    agent_run_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("agent_runs.id", ondelete="SET NULL")
    )
    event_type: Mapped[OpportunityEventType] = mapped_column(
        enum_column(OpportunityEventType, "opportunity_event_type"), nullable=False
    )
    payload: Mapped[dict[str, Any]] = mapped_column(default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, server_default=func.now(), nullable=False
    )

    opportunity: Mapped[Opportunity] = relationship(back_populates="events")
