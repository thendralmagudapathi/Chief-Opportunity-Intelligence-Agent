"""Initial schema.

Creates the 18 Phase 1 entities. Enum values are written out literally rather
than imported from ``app.models.enums`` so this revision stays a frozen snapshot
when the application's enums grow.

PostgreSQL-only objects (the ``vector`` extension, HNSW vector indexes and GIN
full-text indexes) are guarded by a dialect check so the same revision applies
to the SQLite database used by the test suite.

Revision ID: 0001_initial_schema
Revises:
Created: 2026-08-16
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial_schema"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Must equal ``app.db.constants.EMBEDDING_DIM``; startup asserts they agree.
EMBEDDING_DIM = 768


def _dialect() -> str:
    return op.get_context().dialect.name


def _is_postgres() -> bool:
    return _dialect() == "postgresql"


def _enum(name: str, *values: str) -> sa.Enum:
    return sa.Enum(*values, name=name, native_enum=False, create_constraint=True, length=40)


def _json() -> sa.types.TypeEngine:
    return sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def _vector() -> sa.types.TypeEngine:
    if _is_postgres():
        from pgvector.sqlalchemy import Vector

        return Vector(EMBEDDING_DIM)
    return sa.JSON()


def _uuid_pk() -> sa.Column:
    return sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False)


def _timestamps() -> tuple[sa.Column, sa.Column]:
    return (
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )


OBJECTIVE_PROFILES = (
    "career",
    "income",
    "business",
    "learning",
    "networking",
    "startup",
    "research",
)


def upgrade() -> None:
    if _is_postgres():
        # Must precede any column of type ``vector``.
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # ---------------------------------------------------------------- users
    op.create_table(
        "users",
        _uuid_pk(),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(255), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("is_superuser", sa.Boolean(), nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.UniqueConstraint("email"),
    )
    op.create_index("ix_users_email", "users", ["email"])

    op.create_table(
        "user_profiles",
        _uuid_pk(),
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("headline", sa.String(255), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("location_country", sa.String(2), nullable=True),
        sa.Column("location_city", sa.String(120), nullable=True),
        sa.Column("timezone", sa.String(64), nullable=True),
        sa.Column("years_experience", sa.Numeric(4, 1), nullable=True),
        sa.Column("salary_expectation_min", sa.Numeric(14, 2), nullable=True),
        sa.Column("salary_expectation_max", sa.Numeric(14, 2), nullable=True),
        sa.Column("salary_currency", sa.String(3), nullable=True),
        sa.Column("skills", _json(), nullable=False),
        sa.Column("work_authorization", _json(), nullable=False),
        sa.Column("education", _json(), nullable=False),
        sa.Column("certifications", _json(), nullable=False),
        sa.Column("languages", _json(), nullable=False),
        sa.Column("interests", _json(), nullable=False),
        sa.Column("preferences", _json(), nullable=False),
        sa.Column("constraints", _json(), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_id"),
    )

    # ---------------------------------------------------------------- goals
    op.create_table(
        "goals",
        _uuid_pk(),
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "objective_profile", _enum("objective_profile", *OBJECTIVE_PROFILES), nullable=False
        ),
        sa.Column("priority", sa.SmallInteger(), nullable=False),
        sa.Column(
            "status",
            _enum("goal_status", "active", "paused", "achieved", "abandoned"),
            nullable=False,
        ),
        sa.Column("deadline", sa.DateTime(timezone=True), nullable=True),
        sa.Column("desired_outcome", sa.Text(), nullable=True),
        sa.Column("constraints", _json(), nullable=False),
        sa.Column("acceptable_tradeoffs", _json(), nullable=False),
        sa.Column("weights_override", _json(), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_goals_user_id_status_priority", "goals", ["user_id", "status", "priority"])

    # ------------------------------------------------------------ documents
    op.create_table(
        "documents",
        _uuid_pk(),
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("filename", sa.String(512), nullable=False),
        sa.Column("content_type", sa.String(128), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("storage_uri", sa.String(1024), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column(
            "doc_type",
            _enum(
                "document_type",
                "resume",
                "cv",
                "cover_letter",
                "portfolio",
                "transcript",
                "certificate",
                "note",
                "other",
            ),
            nullable=False,
        ),
        sa.Column(
            "status",
            _enum("document_status", "pending", "parsing", "indexed", "failed"),
            nullable=False,
        ),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("parsed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("meta", _json(), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_id", "sha256", name="uq_documents_user_id_sha256"),
    )
    op.create_index("ix_documents_user_id", "documents", ["user_id"])

    op.create_table(
        "document_chunks",
        _uuid_pk(),
        sa.Column("document_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=True),
        sa.Column("embedding", _vector(), nullable=True),
        sa.Column("embedding_model", sa.String(128), nullable=True),
        sa.Column("meta", _json(), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "document_id", "chunk_index", name="uq_document_chunks_document_id_chunk_index"
        ),
    )
    op.create_index(
        "ix_document_chunks_user_id_document_id", "document_chunks", ["user_id", "document_id"]
    )

    # -------------------------------------------------------- opportunities
    op.create_table(
        "opportunity_sources",
        _uuid_pk(),
        sa.Column("key", sa.String(64), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column(
            "source_type",
            _enum("source_type", "api", "rss", "feed", "html", "manual"),
            nullable=False,
        ),
        sa.Column("base_url", sa.String(1024), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("requires_auth", sa.Boolean(), nullable=False),
        sa.Column("rate_limit_per_minute", sa.Integer(), nullable=False),
        sa.Column("robots_respected", sa.Boolean(), nullable=False),
        sa.Column("config", _json(), nullable=False),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        *_timestamps(),
        sa.UniqueConstraint("key"),
    )

    op.create_table(
        "opportunities",
        _uuid_pk(),
        sa.Column("source_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("external_id", sa.String(255), nullable=True),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column(
            "category",
            _enum(
                "opportunity_category",
                "job",
                "freelance",
                "consulting",
                "client",
                "startup",
                "grant",
                "fellowship",
                "scholarship",
                "accelerator",
                "incubator",
                "competition",
                "conference",
                "speaking",
                "research",
                "partnership",
                "business",
                "open_source",
                "other",
            ),
            nullable=False,
        ),
        sa.Column("subcategory", sa.String(120), nullable=True),
        sa.Column("organization_name", sa.String(255), nullable=True),
        sa.Column("organization_domain", sa.String(255), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("language", sa.String(8), nullable=True),
        sa.Column("raw", _json(), nullable=True),
        sa.Column("location_country", sa.String(2), nullable=True),
        sa.Column("location_city", sa.String(120), nullable=True),
        sa.Column(
            "remote_status",
            _enum("remote_status", "onsite", "hybrid", "remote", "unknown"),
            nullable=False,
        ),
        sa.Column("compensation_min", sa.Numeric(14, 2), nullable=True),
        sa.Column("compensation_max", sa.Numeric(14, 2), nullable=True),
        sa.Column("compensation_currency", sa.String(3), nullable=True),
        sa.Column(
            "compensation_period",
            _enum("compensation_period", "hour", "day", "month", "year", "project", "total"),
            nullable=True,
        ),
        sa.Column("requirements", _json(), nullable=False),
        sa.Column("eligibility", _json(), nullable=False),
        sa.Column("required_skills", _json(), nullable=False),
        sa.Column("preferred_skills", _json(), nullable=False),
        sa.Column("posted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deadline", sa.DateTime(timezone=True), nullable=True),
        sa.Column("discovered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("freshness_score", sa.Float(), nullable=True),
        sa.Column("source_url", sa.String(2048), nullable=False),
        sa.Column("canonical_url", sa.String(2048), nullable=True),
        sa.Column("content_hash", sa.String(64), nullable=True),
        sa.Column("simhash", sa.BigInteger(), nullable=True),
        sa.Column(
            "status",
            _enum(
                "opportunity_status",
                "discovered",
                "enriched",
                "qualified",
                "scored",
                "recommended",
                "archived",
                "expired",
                "rejected",
                "duplicate",
            ),
            nullable=False,
        ),
        sa.Column("duplicate_of_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("embedding", _vector(), nullable=True),
        sa.Column("embedding_model", sa.String(128), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(["source_id"], ["opportunity_sources.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["duplicate_of_id"], ["opportunities.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("content_hash"),
        sa.UniqueConstraint(
            "source_id", "external_id", name="uq_opportunities_source_id_external_id"
        ),
    )
    op.create_index("ix_opportunities_category_status", "opportunities", ["category", "status"])
    op.create_index(
        "ix_opportunities_organization_domain_title",
        "opportunities",
        ["organization_domain", "title"],
    )
    op.create_index("ix_opportunities_deadline", "opportunities", ["deadline"])
    op.create_index("ix_opportunities_discovered_at", "opportunities", ["discovered_at"])
    op.create_index("ix_opportunities_canonical_url", "opportunities", ["canonical_url"])

    # ------------------------------------------------------ agent execution
    op.create_table(
        "agent_runs",
        _uuid_pk(),
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("goal_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("trace_id", sa.String(64), nullable=False),
        sa.Column(
            "run_type",
            _enum(
                "agent_run_type",
                "search",
                "investigate",
                "refresh",
                "evaluate",
                "scheduled",
                "research",
            ),
            nullable=False,
        ),
        sa.Column(
            "status",
            _enum(
                "agent_run_status",
                "pending",
                "running",
                "awaiting_approval",
                "succeeded",
                "failed",
                "cancelled",
            ),
            nullable=False,
        ),
        sa.Column("objective_text", sa.Text(), nullable=True),
        sa.Column("graph_version", sa.String(32), nullable=True),
        sa.Column("iterations", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("cost_usd", sa.Numeric(10, 6), nullable=False),
        sa.Column("budget", _json(), nullable=False),
        sa.Column("degraded", sa.Boolean(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("result", _json(), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["goal_id"], ["goals.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("trace_id"),
    )
    op.create_index("ix_agent_runs_user_id_created_at", "agent_runs", ["user_id", "created_at"])

    op.create_table(
        "agent_tasks",
        _uuid_pk(),
        sa.Column("agent_run_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("parent_task_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("agent_name", sa.String(64), nullable=False),
        sa.Column("capability", sa.String(64), nullable=True),
        sa.Column(
            "status",
            _enum("agent_task_status", "pending", "running", "succeeded", "failed", "skipped"),
            nullable=False,
        ),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("input", _json(), nullable=True),
        sa.Column("output", _json(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("cost_usd", sa.Numeric(10, 6), nullable=False),
        sa.Column("model_name", sa.String(128), nullable=True),
        sa.Column("prompt_version", sa.String(64), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(["agent_run_id"], ["agent_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["parent_task_id"], ["agent_tasks.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_agent_tasks_agent_run_id_created_at", "agent_tasks", ["agent_run_id", "created_at"]
    )

    op.create_table(
        "tool_calls",
        _uuid_pk(),
        sa.Column("agent_run_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("agent_task_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("tool_name", sa.String(64), nullable=False),
        sa.Column("transport", _enum("tool_transport", "native", "mcp"), nullable=False),
        sa.Column(
            "status",
            _enum("tool_call_status", "succeeded", "failed", "denied", "timeout"),
            nullable=False,
        ),
        sa.Column("arguments", _json(), nullable=True),
        sa.Column("result", _json(), nullable=True),
        sa.Column("result_hash", sa.String(64), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("cost_usd", sa.Numeric(10, 6), nullable=False),
        sa.Column("cache_hit", sa.Boolean(), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["agent_run_id"], ["agent_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["agent_task_id"], ["agent_tasks.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_tool_calls_agent_run_id_created_at", "tool_calls", ["agent_run_id", "created_at"]
    )

    # --------------------------------------------- scores, evidence, events
    op.create_table(
        "opportunity_scores",
        _uuid_pk(),
        sa.Column("opportunity_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("goal_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("agent_run_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("scoring_profile", _enum("scoring_profile", *OBJECTIVE_PROFILES), nullable=False),
        sa.Column("weights_version", sa.String(64), nullable=False),
        sa.Column("engine_version", sa.String(32), nullable=False),
        sa.Column("fit_score", sa.Numeric(6, 4), nullable=True),
        sa.Column("value_score", sa.Numeric(6, 4), nullable=True),
        sa.Column("probability_of_success", sa.Numeric(6, 4), nullable=True),
        sa.Column("strategic_value", sa.Numeric(6, 4), nullable=True),
        sa.Column("time_sensitivity", sa.Numeric(6, 4), nullable=True),
        sa.Column("effort_score", sa.Numeric(6, 4), nullable=True),
        sa.Column("risk_score", sa.Numeric(6, 4), nullable=True),
        sa.Column("learning_value", sa.Numeric(6, 4), nullable=True),
        sa.Column("network_value", sa.Numeric(6, 4), nullable=True),
        sa.Column("long_term_value", sa.Numeric(6, 4), nullable=True),
        sa.Column("overall_score", sa.Numeric(6, 2), nullable=False),
        sa.Column("confidence", sa.Numeric(6, 4), nullable=True),
        sa.Column(
            "recommendation",
            _enum(
                "recommendation",
                "STRONGLY_PURSUE",
                "PURSUE",
                "CONSIDER",
                "WAIT",
                "LOW_PRIORITY",
                "IGNORE",
                "INELIGIBLE",
            ),
            nullable=True,
        ),
        sa.Column("factors", _json(), nullable=False),
        sa.Column("explanation", _json(), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(["opportunity_id"], ["opportunities.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["goal_id"], ["goals.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["agent_run_id"], ["agent_runs.id"], ondelete="SET NULL"),
        sa.UniqueConstraint(
            "opportunity_id",
            "goal_id",
            "weights_version",
            name="uq_opportunity_scores_opportunity_id_goal_id_weights_version",
        ),
    )
    op.create_index(
        "ix_opportunity_scores_goal_id_overall_score",
        "opportunity_scores",
        ["goal_id", "overall_score"],
    )

    op.create_table(
        "opportunity_evidence",
        _uuid_pk(),
        sa.Column("opportunity_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("agent_run_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("agent_name", sa.String(64), nullable=True),
        sa.Column("claim", sa.Text(), nullable=False),
        sa.Column(
            "claim_type",
            _enum("claim_type", "FACT", "INFERENCE", "ESTIMATE", "ASSUMPTION", "UNKNOWN"),
            nullable=False,
        ),
        sa.Column(
            "stance",
            _enum("evidence_stance", "supports", "contradicts", "neutral"),
            nullable=False,
        ),
        sa.Column("value", _json(), nullable=True),
        sa.Column("source_url", sa.String(2048), nullable=True),
        sa.Column("source_title", sa.String(512), nullable=True),
        sa.Column("source_trust", sa.String(32), nullable=True),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("confidence", sa.Numeric(6, 4), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(["opportunity_id"], ["opportunities.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["agent_run_id"], ["agent_runs.id"], ondelete="SET NULL"),
    )
    op.create_index(
        "ix_opportunity_evidence_opportunity_id_stance",
        "opportunity_evidence",
        ["opportunity_id", "stance"],
    )

    op.create_table(
        "opportunity_events",
        _uuid_pk(),
        sa.Column("opportunity_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("agent_run_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column(
            "event_type",
            _enum(
                "opportunity_event_type",
                "discovered",
                "deduplicated",
                "enriched",
                "scored",
                "recommended",
                "viewed",
                "dismissed",
                "revalidated",
                "expired",
                "status_changed",
            ),
            nullable=False,
        ),
        sa.Column("payload", _json(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["opportunity_id"], ["opportunities.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["agent_run_id"], ["agent_runs.id"], ondelete="SET NULL"),
    )
    op.create_index(
        "ix_opportunity_events_opportunity_id_created_at",
        "opportunity_events",
        ["opportunity_id", "created_at"],
    )

    # ------------------------------------------------ applications, outcomes
    op.create_table(
        "applications",
        _uuid_pk(),
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("opportunity_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column(
            "status",
            _enum(
                "application_status",
                "draft",
                "awaiting_approval",
                "approved",
                "submitted",
                "withdrawn",
                "rejected",
                "accepted",
            ),
            nullable=False,
        ),
        sa.Column("channel", sa.String(64), nullable=True),
        sa.Column("artifacts", _json(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("approved_by_user_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["opportunity_id"], ["opportunities.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_applications_user_id_status", "applications", ["user_id", "status"])

    op.create_table(
        "outcomes",
        _uuid_pk(),
        sa.Column("application_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("opportunity_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column(
            "outcome",
            _enum(
                "outcome_type",
                "applied",
                "interviewed",
                "rejected",
                "accepted",
                "ignored",
                "expired",
                "successful",
            ),
            nullable=False,
        ),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("details", _json(), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["application_id"], ["applications.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["opportunity_id"], ["opportunities.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_outcomes_user_id_outcome", "outcomes", ["user_id", "outcome"])

    # --------------------------------------------- memory, feedback, evals
    op.create_table(
        "memory_records",
        _uuid_pk(),
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column(
            "memory_type",
            _enum("memory_type", "episodic", "semantic", "outcome"),
            nullable=False,
        ),
        sa.Column("key", sa.String(255), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("embedding", _vector(), nullable=True),
        sa.Column("importance", sa.Numeric(6, 4), nullable=True),
        sa.Column("confidence", sa.Numeric(6, 4), nullable=True),
        sa.Column("provenance", _json(), nullable=False),
        sa.Column("source_ref", sa.String(255), nullable=True),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("valid_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("superseded_by_id", sa.Uuid(as_uuid=True), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["superseded_by_id"], ["memory_records.id"], ondelete="SET NULL"),
    )
    op.create_index(
        "ix_memory_records_user_id_memory_type_valid_to",
        "memory_records",
        ["user_id", "memory_type", "valid_to"],
    )

    op.create_table(
        "feedback",
        _uuid_pk(),
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("opportunity_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("agent_run_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column(
            "signal",
            _enum(
                "feedback_signal",
                "relevant",
                "irrelevant",
                "high_value",
                "not_eligible",
                "too_much_effort",
                "low_value",
                "applied",
                "successful",
            ),
            nullable=False,
        ),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("payload", _json(), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["opportunity_id"], ["opportunities.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["agent_run_id"], ["agent_runs.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_feedback_user_id_created_at", "feedback", ["user_id", "created_at"])

    op.create_table(
        "evaluation_runs",
        _uuid_pk(),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("suite", sa.String(64), nullable=False),
        sa.Column("dataset_name", sa.String(128), nullable=False),
        sa.Column("dataset_version", sa.String(64), nullable=False),
        sa.Column("git_sha", sa.String(40), nullable=True),
        sa.Column(
            "status",
            _enum("evaluation_status", "pending", "running", "succeeded", "failed"),
            nullable=False,
        ),
        sa.Column("config", _json(), nullable=False),
        sa.Column("metrics", _json(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("mlflow_run_id", sa.String(64), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
    )
    op.create_index(
        "ix_evaluation_runs_dataset_name_created_at",
        "evaluation_runs",
        ["dataset_name", "created_at"],
    )

    _create_postgres_only_indexes()


def _create_postgres_only_indexes() -> None:
    """Vector and full-text indexes.

    HNSW rather than IVFFlat: the corpus grows continuously, and IVFFlat needs a
    representative sample at build time to give useful recall.
    """
    if not _is_postgres():
        return

    op.execute(
        "CREATE INDEX ix_document_chunks_embedding_hnsw ON document_chunks "
        "USING hnsw (embedding vector_cosine_ops)"
    )
    op.execute(
        "CREATE INDEX ix_opportunities_embedding_hnsw ON opportunities "
        "USING hnsw (embedding vector_cosine_ops)"
    )
    op.execute(
        "CREATE INDEX ix_memory_records_embedding_hnsw ON memory_records "
        "USING hnsw (embedding vector_cosine_ops)"
    )
    # Lexical half of hybrid search. The two-argument to_tsvector form with a
    # literal configuration is IMMUTABLE, so it is indexable.
    op.execute(
        "CREATE INDEX ix_document_chunks_content_fts ON document_chunks "
        "USING gin (to_tsvector('english', content))"
    )
    op.execute(
        "CREATE INDEX ix_opportunities_fts ON opportunities USING gin ("
        "to_tsvector('english', coalesce(title, '') || ' ' || coalesce(description, '')))"
    )


def downgrade() -> None:
    for table in (
        "evaluation_runs",
        "feedback",
        "memory_records",
        "outcomes",
        "applications",
        "opportunity_events",
        "opportunity_evidence",
        "opportunity_scores",
        "tool_calls",
        "agent_tasks",
        "agent_runs",
        "opportunities",
        "opportunity_sources",
        "document_chunks",
        "documents",
        "goals",
        "user_profiles",
        "users",
    ):
        op.drop_table(table)
    # The vector extension is intentionally left in place: other schemas in the
    # same database may depend on it.
