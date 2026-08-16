"""Opportunity read access.

Filtering, keyset pagination and the detail projection. Discovery, scoring and
freshness live in sibling services; this module only reads what they wrote.
"""

from __future__ import annotations

import base64
import binascii
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Literal

from sqlalchemy import ColumnElement, Select, and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError, ValidationError
from app.models.opportunity import Opportunity, OpportunityEvidence, OpportunityScore
from app.schemas.opportunity import OpportunityFilters
from app.services.lifecycle import INACTIVE

SortKey = Literal["score", "deadline", "recent"]

#: Sentinel that pushes missing deadlines to the end of an ascending sort while
#: keeping the sort expression non-null, which keeps keyset paging simple.
FAR_FUTURE = datetime(9999, 12, 31, tzinfo=UTC)
NO_SCORE = Decimal("-1")


@dataclass(frozen=True, slots=True)
class Cursor:
    """Opaque keyset cursor: the sort value and id of the last row returned."""

    value: str
    row_id: uuid.UUID

    def encode(self) -> str:
        payload = json.dumps({"v": self.value, "id": str(self.row_id)}, separators=(",", ":"))
        return base64.urlsafe_b64encode(payload.encode()).decode().rstrip("=")

    @classmethod
    def decode(cls, raw: str) -> Cursor:
        try:
            padded = raw + "=" * (-len(raw) % 4)
            data = json.loads(base64.urlsafe_b64decode(padded.encode()))
            return cls(value=str(data["v"]), row_id=uuid.UUID(str(data["id"])))
        except (ValueError, KeyError, binascii.Error) as exc:
            raise ValidationError("Malformed pagination cursor") from exc


@dataclass(frozen=True, slots=True)
class OpportunityRow:
    opportunity: Opportunity
    score: OpportunityScore | None


@dataclass(frozen=True, slots=True)
class OpportunityPage:
    rows: list[OpportunityRow]
    next_cursor: str | None
    has_more: bool


class OpportunityService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # -- helpers ----------------------------------------------------------

    def _latest_score_join(self, goal_id: uuid.UUID | None) -> Any:
        """Correlated subquery selecting the most recent score row.

        Scores are append-only, so "the score" of an opportunity is always the
        newest row for the goal in question rather than a mutable column.
        """
        stmt = select(OpportunityScore.id).where(OpportunityScore.opportunity_id == Opportunity.id)
        if goal_id is not None:
            stmt = stmt.where(OpportunityScore.goal_id == goal_id)
        return (
            stmt.order_by(
                OpportunityScore.computed_at.desc().nullslast(),
                OpportunityScore.created_at.desc(),
            )
            .limit(1)
            .correlate(Opportunity)
            .scalar_subquery()
        )

    def _sort_expression(self, sort: SortKey) -> tuple[ColumnElement[Any], bool]:
        """Return ``(expression, descending)``; the expression is never NULL."""
        if sort == "score":
            return func.coalesce(OpportunityScore.overall_score, NO_SCORE), True
        if sort == "deadline":
            return func.coalesce(Opportunity.deadline, FAR_FUTURE), False
        return Opportunity.created_at.expression, True

    def _apply_filters(self, stmt: Select[Any], filters: OpportunityFilters) -> Select[Any]:
        if filters.category is not None:
            stmt = stmt.where(Opportunity.category == filters.category)
        if filters.status is not None:
            stmt = stmt.where(Opportunity.status == filters.status)
        elif not filters.include_expired:
            # Stale and duplicate rows are never recommended (brief §25).
            stmt = stmt.where(Opportunity.status.not_in(INACTIVE))
        if filters.country is not None:
            stmt = stmt.where(Opportunity.location_country == filters.country.upper())
        if filters.remote_status is not None:
            stmt = stmt.where(Opportunity.remote_status == filters.remote_status)
        if filters.deadline_before is not None:
            stmt = stmt.where(Opportunity.deadline.is_not(None)).where(
                Opportunity.deadline <= filters.deadline_before
            )
        if filters.min_score is not None:
            stmt = stmt.where(OpportunityScore.overall_score >= filters.min_score)
        if filters.q:
            # Deliberately a simple ILIKE: real search is the hybrid retrieval
            # path added in Phase 3, not a half-built full-text query here.
            pattern = f"%{filters.q.strip()}%"
            stmt = stmt.where(
                or_(
                    Opportunity.title.ilike(pattern),
                    Opportunity.organization_name.ilike(pattern),
                    Opportunity.summary.ilike(pattern),
                )
            )
        return stmt

    @staticmethod
    def _cursor_value(row: OpportunityRow, sort: SortKey) -> str:
        if sort == "score":
            score = row.score.overall_score if row.score else None
            return str(score if score is not None else NO_SCORE)
        if sort == "deadline":
            return (row.opportunity.deadline or FAR_FUTURE).isoformat()
        return row.opportunity.created_at.isoformat()

    @staticmethod
    def _parse_cursor_value(cursor: Cursor, sort: SortKey) -> Any:
        try:
            if sort == "score":
                return Decimal(cursor.value)
            if sort in ("deadline", "recent"):
                return datetime.fromisoformat(cursor.value)
        except (InvalidOperation, ValueError) as exc:
            raise ValidationError("Malformed pagination cursor") from exc
        raise ValidationError("Unsupported sort key")

    # -- queries ----------------------------------------------------------

    async def list_opportunities(
        self,
        filters: OpportunityFilters,
        *,
        limit: int = 20,
        cursor: str | None = None,
        sort: SortKey = "score",
    ) -> OpportunityPage:
        score_alias = self._latest_score_join(filters.goal_id)
        stmt = select(Opportunity, OpportunityScore).outerjoin(
            OpportunityScore, OpportunityScore.id == score_alias
        )
        stmt = self._apply_filters(stmt, filters)

        sort_expr, descending = self._sort_expression(sort)
        if cursor is not None:
            parsed = Cursor.decode(cursor)
            boundary = self._parse_cursor_value(parsed, sort)
            # Expressed as OR rather than a row-value comparison so the same SQL
            # runs on PostgreSQL and SQLite.
            if descending:
                stmt = stmt.where(
                    or_(
                        sort_expr < boundary,
                        and_(sort_expr == boundary, Opportunity.id < parsed.row_id),
                    )
                )
            else:
                stmt = stmt.where(
                    or_(
                        sort_expr > boundary,
                        and_(sort_expr == boundary, Opportunity.id > parsed.row_id),
                    )
                )

        order = (
            (sort_expr.desc(), Opportunity.id.desc())
            if descending
            else (sort_expr.asc(), Opportunity.id.asc())
        )
        stmt = stmt.order_by(*order).limit(limit + 1)

        result = await self.session.execute(stmt)
        rows = [OpportunityRow(opportunity=o, score=s) for o, s in result.all()]

        has_more = len(rows) > limit
        rows = rows[:limit]
        next_cursor = (
            Cursor(
                value=self._cursor_value(rows[-1], sort), row_id=rows[-1].opportunity.id
            ).encode()
            if has_more and rows
            else None
        )
        return OpportunityPage(rows=rows, next_cursor=next_cursor, has_more=has_more)

    async def get_opportunity(
        self, opportunity_id: uuid.UUID, goal_id: uuid.UUID | None = None
    ) -> OpportunityRow:
        stmt = (
            select(Opportunity, OpportunityScore)
            .outerjoin(OpportunityScore, OpportunityScore.id == self._latest_score_join(goal_id))
            .where(Opportunity.id == opportunity_id)
        )
        result = await self.session.execute(stmt)
        row = result.first()
        if row is None:
            raise NotFoundError("Opportunity not found")
        return OpportunityRow(opportunity=row[0], score=row[1])

    async def list_evidence(self, opportunity_id: uuid.UUID) -> list[OpportunityEvidence]:
        result = await self.session.execute(
            select(OpportunityEvidence)
            .where(OpportunityEvidence.opportunity_id == opportunity_id)
            .order_by(OpportunityEvidence.created_at.desc())
            .limit(100)
        )
        return list(result.scalars().all())
