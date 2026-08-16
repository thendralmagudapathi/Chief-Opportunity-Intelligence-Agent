"""Persistence around the scoring engine.

The engine itself is pure; this is the part that reads what it needs, calls it,
and writes the result. Keeping the split sharp is what allows a stored score to
be recomputed offline: everything that influenced it is either in ``factors`` or
named by ``weights_version``.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.core.logging import get_logger
from app.models.enums import OpportunityStatus, Recommendation
from app.models.goal import Goal
from app.models.opportunity import Opportunity, OpportunityScore
from app.models.user import UserProfile
from app.services import factors as factor_derivation
from app.services import lifecycle
from app.services.ingestion import IngestionService
from app.services.scoring import ScoreResult, score, weights_for

logger = get_logger(__name__)


class ScoringService:
    """Scores opportunities against a goal and stores the result."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self._lifecycle = IngestionService(session)

    async def score_opportunity(
        self,
        opportunity: Opportunity,
        goal: Goal,
        *,
        profile: UserProfile | None = None,
        now: datetime | None = None,
    ) -> OpportunityScore:
        moment = (now or datetime.now(UTC)).astimezone(UTC)
        weights = weights_for(goal.objective_profile, goal.weights_override)

        derived = factor_derivation.derive(opportunity, profile=profile, goal=goal, now=moment)
        result = score(
            derived.values,
            weights,
            eligible=derived.eligible,
            days_to_deadline=derived.days_to_deadline,
        )

        row = await self._upsert(opportunity, goal, result, derived, moment)

        # Scoring is what moves an opportunity along the pipeline; a row that has
        # been scored is no longer merely discovered.
        if opportunity.status not in lifecycle.INACTIVE:
            await self._lifecycle.set_status(opportunity, _target_status(result), reason="scored")
        return row

    async def score_goal(
        self,
        goal: Goal,
        *,
        opportunity_ids: Iterable[uuid.UUID] | None = None,
        now: datetime | None = None,
        limit: int = 500,
    ) -> Sequence[OpportunityScore]:
        """Score every eligible opportunity against one goal."""
        profile = await self._profile_for(goal.user_id)

        stmt = select(Opportunity).where(Opportunity.status.not_in(lifecycle.INACTIVE))
        if opportunity_ids is not None:
            ids = list(opportunity_ids)
            if not ids:
                return []
            stmt = stmt.where(Opportunity.id.in_(ids))
        stmt = stmt.order_by(Opportunity.created_at).limit(limit)

        opportunities = (await self.session.execute(stmt)).scalars().all()
        return [
            await self.score_opportunity(opportunity, goal, profile=profile, now=now)
            for opportunity in opportunities
        ]

    async def score_goal_by_id(
        self, goal_id: uuid.UUID, user_id: uuid.UUID, *, now: datetime | None = None
    ) -> Sequence[OpportunityScore]:
        goal = (
            await self.session.execute(
                select(Goal).where(Goal.id == goal_id, Goal.user_id == user_id)
            )
        ).scalar_one_or_none()
        if goal is None:
            raise NotFoundError("Goal not found")
        return await self.score_goal(goal, now=now)

    async def _profile_for(self, user_id: uuid.UUID) -> UserProfile | None:
        return (
            await self.session.execute(select(UserProfile).where(UserProfile.user_id == user_id))
        ).scalar_one_or_none()

    async def _upsert(
        self,
        opportunity: Opportunity,
        goal: Goal,
        result: ScoreResult,
        derived: factor_derivation.DerivedFactors,
        moment: datetime,
    ) -> OpportunityScore:
        """Write the score for this (opportunity, goal, weights) combination.

        The table is unique on those three, so re-scoring under an unchanged
        weight vector updates in place rather than inserting. That is not a
        weaker guarantee than it looks: the engine is deterministic, so the only
        way the numbers move is that the underlying factors moved, and the new
        row records the factors that produced them. Comparing across weight
        versions — the case the append-only design exists for — still yields two
        separate rows.
        """
        existing = (
            await self.session.execute(
                select(OpportunityScore).where(
                    OpportunityScore.opportunity_id == opportunity.id,
                    OpportunityScore.goal_id == goal.id,
                    OpportunityScore.weights_version == result.weights_version,
                )
            )
        ).scalar_one_or_none()

        row = existing or OpportunityScore(
            opportunity_id=opportunity.id,
            goal_id=goal.id,
            user_id=goal.user_id,
            weights_version=result.weights_version,
        )

        row.scoring_profile = goal.objective_profile
        row.engine_version = result.engine_version
        row.overall_score = result.overall
        row.confidence = result.confidence
        row.recommendation = result.recommendation
        row.computed_at = moment
        row.factors = {**result.as_factors(), "rationale": derived.rationale}
        row.explanation = result.explanation

        for dimension, value in result.dimensions.items():
            setattr(row, dimension.value, value)

        if existing is None:
            self.session.add(row)
        await self.session.flush()
        return row


def _target_status(result: ScoreResult) -> OpportunityStatus:
    """Where scoring leaves an opportunity in the pipeline.

    A re-score that no longer clears the bar returns the row to SCORED, so a
    recommendation that stopped being justified is withdrawn rather than left
    standing.
    """
    if result.recommendation in (Recommendation.STRONGLY_PURSUE, Recommendation.PURSUE):
        return OpportunityStatus.RECOMMENDED
    return OpportunityStatus.SCORED
