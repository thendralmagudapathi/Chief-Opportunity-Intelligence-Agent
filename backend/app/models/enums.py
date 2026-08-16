"""Domain enumerations.

These are shared by the ORM, the Pydantic schemas and the agent contracts, so
there is exactly one definition of "what statuses exist". They are stored as
``VARCHAR`` with a ``CHECK`` constraint rather than native PostgreSQL enums:
adding a value then costs one cheap migration instead of a type rewrite, and the
same DDL runs on SQLite in tests.
"""

from __future__ import annotations

from enum import StrEnum
from typing import TypeVar

from sqlalchemy import Enum as SAEnum

E = TypeVar("E", bound=StrEnum)


def enum_column(enum_cls: type[E], name: str, length: int = 40) -> SAEnum:
    """Build a portable, value-persisted enum column type.

    ``create_constraint=True`` adds a database-level ``CHECK`` so an invalid
    status cannot be written by a migration, a fixture or a stray SQL script —
    application validation alone is not enough for a table this long-lived.
    """
    return SAEnum(
        enum_cls,
        name=name,
        native_enum=False,
        create_constraint=True,
        length=length,
        validate_strings=True,
        values_callable=lambda cls: [member.value for member in cls],
    )


# --------------------------------------------------------------------------
# Objectives and goals
# --------------------------------------------------------------------------


class ObjectiveProfile(StrEnum):
    """Selects the default scoring weight vector for a goal."""

    CAREER = "career"
    INCOME = "income"
    BUSINESS = "business"
    LEARNING = "learning"
    NETWORKING = "networking"
    STARTUP = "startup"
    RESEARCH = "research"


class GoalStatus(StrEnum):
    ACTIVE = "active"
    PAUSED = "paused"
    ACHIEVED = "achieved"
    ABANDONED = "abandoned"


# --------------------------------------------------------------------------
# Documents
# --------------------------------------------------------------------------


class DocumentType(StrEnum):
    RESUME = "resume"
    CV = "cv"
    COVER_LETTER = "cover_letter"
    PORTFOLIO = "portfolio"
    TRANSCRIPT = "transcript"
    CERTIFICATE = "certificate"
    NOTE = "note"
    OTHER = "other"


class DocumentStatus(StrEnum):
    PENDING = "pending"
    PARSING = "parsing"
    INDEXED = "indexed"
    FAILED = "failed"


# --------------------------------------------------------------------------
# Opportunities
# --------------------------------------------------------------------------


class SourceType(StrEnum):
    API = "api"
    RSS = "rss"
    FEED = "feed"
    HTML = "html"
    MANUAL = "manual"


class OpportunityCategory(StrEnum):
    """Deliberately broad: the domain model is not job-shaped."""

    JOB = "job"
    FREELANCE = "freelance"
    CONSULTING = "consulting"
    CLIENT = "client"
    STARTUP = "startup"
    GRANT = "grant"
    FELLOWSHIP = "fellowship"
    SCHOLARSHIP = "scholarship"
    ACCELERATOR = "accelerator"
    INCUBATOR = "incubator"
    COMPETITION = "competition"
    CONFERENCE = "conference"
    SPEAKING = "speaking"
    RESEARCH = "research"
    PARTNERSHIP = "partnership"
    BUSINESS = "business"
    OPEN_SOURCE = "open_source"
    OTHER = "other"


class RemoteStatus(StrEnum):
    ONSITE = "onsite"
    HYBRID = "hybrid"
    REMOTE = "remote"
    UNKNOWN = "unknown"


class CompensationPeriod(StrEnum):
    HOUR = "hour"
    DAY = "day"
    MONTH = "month"
    YEAR = "year"
    PROJECT = "project"
    TOTAL = "total"


class OpportunityStatus(StrEnum):
    DISCOVERED = "discovered"
    ENRICHED = "enriched"
    QUALIFIED = "qualified"
    SCORED = "scored"
    RECOMMENDED = "recommended"
    ARCHIVED = "archived"
    EXPIRED = "expired"
    REJECTED = "rejected"
    DUPLICATE = "duplicate"


class OpportunityEventType(StrEnum):
    DISCOVERED = "discovered"
    DEDUPLICATED = "deduplicated"
    ENRICHED = "enriched"
    SCORED = "scored"
    RECOMMENDED = "recommended"
    VIEWED = "viewed"
    DISMISSED = "dismissed"
    REVALIDATED = "revalidated"
    EXPIRED = "expired"
    STATUS_CHANGED = "status_changed"


# --------------------------------------------------------------------------
# Evidence and decisions
# --------------------------------------------------------------------------


class ClaimType(StrEnum):
    """An inference must never be presented as a fact (brief §36)."""

    FACT = "FACT"
    INFERENCE = "INFERENCE"
    ESTIMATE = "ESTIMATE"
    ASSUMPTION = "ASSUMPTION"
    UNKNOWN = "UNKNOWN"


class EvidenceStance(StrEnum):
    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"
    NEUTRAL = "neutral"


class RequirementState(StrEnum):
    MET = "met"
    NOT_MET = "not_met"
    UNKNOWN = "unknown"


class RiskSeverity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Recommendation(StrEnum):
    STRONGLY_PURSUE = "STRONGLY_PURSUE"
    PURSUE = "PURSUE"
    CONSIDER = "CONSIDER"
    WAIT = "WAIT"
    LOW_PRIORITY = "LOW_PRIORITY"
    IGNORE = "IGNORE"
    INELIGIBLE = "INELIGIBLE"


# --------------------------------------------------------------------------
# Applications and outcomes
# --------------------------------------------------------------------------


class ApplicationStatus(StrEnum):
    DRAFT = "draft"
    AWAITING_APPROVAL = "awaiting_approval"
    APPROVED = "approved"
    SUBMITTED = "submitted"
    WITHDRAWN = "withdrawn"
    REJECTED = "rejected"
    ACCEPTED = "accepted"


class OutcomeType(StrEnum):
    APPLIED = "applied"
    INTERVIEWED = "interviewed"
    REJECTED = "rejected"
    ACCEPTED = "accepted"
    IGNORED = "ignored"
    EXPIRED = "expired"
    SUCCESSFUL = "successful"


# --------------------------------------------------------------------------
# Agent execution
# --------------------------------------------------------------------------


class AgentRunType(StrEnum):
    SEARCH = "search"
    INVESTIGATE = "investigate"
    REFRESH = "refresh"
    EVALUATE = "evaluate"
    SCHEDULED = "scheduled"
    RESEARCH = "research"


class AgentRunStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    AWAITING_APPROVAL = "awaiting_approval"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AgentTaskStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"


class ToolTransport(StrEnum):
    NATIVE = "native"
    MCP = "mcp"


class ToolCallStatus(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    DENIED = "denied"
    TIMEOUT = "timeout"


# --------------------------------------------------------------------------
# Memory, feedback, evaluation
# --------------------------------------------------------------------------


class MemoryType(StrEnum):
    EPISODIC = "episodic"
    SEMANTIC = "semantic"
    OUTCOME = "outcome"


class FeedbackSignal(StrEnum):
    RELEVANT = "relevant"
    IRRELEVANT = "irrelevant"
    HIGH_VALUE = "high_value"
    NOT_ELIGIBLE = "not_eligible"
    TOO_MUCH_EFFORT = "too_much_effort"
    LOW_VALUE = "low_value"
    APPLIED = "applied"
    SUCCESSFUL = "successful"


class EvaluationStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
