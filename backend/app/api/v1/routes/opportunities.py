"""Opportunity read and refresh endpoints.

Search and investigate land in Phase 4. They are absent rather than stubbed, so
the OpenAPI schema never advertises a capability the system does not have.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, Query

from app.api.deps import CurrentUser, IngestionServiceDep, OpportunityServiceDep
from app.models.enums import OpportunityCategory, OpportunityStatus, RemoteStatus
from app.models.opportunity import Opportunity, OpportunityScore
from app.schemas.common import Page
from app.schemas.opportunity import (
    Compensation,
    EvidenceRead,
    Freshness,
    OpportunityColumns,
    OpportunityFilters,
    OpportunityListItem,
    OpportunityRead,
    ScoreDimensions,
    ScoreRead,
)

router = APIRouter(prefix="/opportunities", tags=["opportunities"])


def _to_score(score: OpportunityScore | None) -> ScoreRead | None:
    if score is None:
        return None
    return ScoreRead(
        overall_score=score.overall_score,
        confidence=score.confidence,
        scoring_profile=score.scoring_profile,
        weights_version=score.weights_version,
        engine_version=score.engine_version,
        goal_id=score.goal_id,
        computed_at=score.computed_at,
        dimensions=ScoreDimensions(
            fit_score=score.fit_score,
            value_score=score.value_score,
            probability_of_success=score.probability_of_success,
            strategic_value=score.strategic_value,
            time_sensitivity=score.time_sensitivity,
            effort_score=score.effort_score,
            risk_score=score.risk_score,
            learning_value=score.learning_value,
            network_value=score.network_value,
            long_term_value=score.long_term_value,
        ),
    )


def _to_list_item(opportunity: Opportunity, score: OpportunityScore | None) -> OpportunityListItem:
    item = OpportunityListItem.model_validate(opportunity)
    if score is not None:
        item.overall_score = score.overall_score
        item.recommendation = score.recommendation
    return item


@router.get("", response_model=Page[OpportunityListItem], summary="List ranked opportunities")
async def list_opportunities(
    _user: CurrentUser,
    service: OpportunityServiceDep,
    # Declared explicitly rather than as a bound Pydantic query model: the
    # flattening behaviour differs across FastAPI versions, and an explicit
    # signature also documents each filter individually in the OpenAPI schema.
    category: OpportunityCategory | None = None,
    status: OpportunityStatus | None = None,
    country: Annotated[str | None, Query(min_length=2, max_length=2)] = None,
    remote_status: RemoteStatus | None = None,
    goal_id: uuid.UUID | None = None,
    min_score: Annotated[Decimal | None, Query(ge=0, le=100)] = None,
    deadline_before: datetime | None = None,
    q: Annotated[str | None, Query(max_length=200)] = None,
    include_expired: bool = False,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    cursor: str | None = None,
    sort: Literal["score", "deadline", "recent"] = "score",
) -> Page[OpportunityListItem]:
    filters = OpportunityFilters(
        category=category,
        status=status,
        country=country,
        remote_status=remote_status,
        goal_id=goal_id,
        min_score=min_score,
        deadline_before=deadline_before,
        q=q,
        include_expired=include_expired,
    )
    page = await service.list_opportunities(filters, limit=limit, cursor=cursor, sort=sort)
    return Page[OpportunityListItem](
        items=[_to_list_item(row.opportunity, row.score) for row in page.rows],
        next_cursor=page.next_cursor,
        has_more=page.has_more,
    )


@router.get("/{opportunity_id}", response_model=OpportunityRead, summary="Opportunity detail")
async def read_opportunity(
    opportunity_id: uuid.UUID,
    _user: CurrentUser,
    service: OpportunityServiceDep,
    goal_id: uuid.UUID | None = None,
) -> OpportunityRead:
    row = await service.get_opportunity(opportunity_id, goal_id)
    opportunity = row.opportunity
    evidence = await service.list_evidence(opportunity_id)

    return OpportunityRead(
        **OpportunityColumns.model_validate(opportunity).model_dump(),
        compensation=Compensation(
            min=opportunity.compensation_min,
            max=opportunity.compensation_max,
            currency=opportunity.compensation_currency,
            period=opportunity.compensation_period,
        ),
        freshness=Freshness(
            discovered_at=opportunity.discovered_at,
            last_verified_at=opportunity.last_verified_at,
            expires_at=opportunity.expires_at,
            score=opportunity.freshness_score,
        ),
        score=_to_score(row.score),
        recommendation=row.score.recommendation if row.score else None,
        explanation=dict(row.score.explanation) if row.score else {},
        evidence=[EvidenceRead.model_validate(e) for e in evidence],
    )


@router.post(
    "/{opportunity_id}/refresh",
    response_model=OpportunityRead,
    summary="Recompute freshness and apply any due expiry",
)
async def refresh_opportunity(
    opportunity_id: uuid.UUID,
    _user: CurrentUser,
    service: OpportunityServiceDep,
    ingestion: IngestionServiceDep,
    goal_id: uuid.UUID | None = None,
) -> OpportunityRead:
    """Re-date an opportunity from what is already stored.

    Re-fetching the source belongs to the discovery pipeline; this recomputes the
    freshness score and expires the row if its deadline has passed, which is what
    keeps closed opportunities out of recommendations between crawls.
    """
    row = await service.get_opportunity(opportunity_id, goal_id)
    await ingestion.refresh(row.opportunity)
    return await read_opportunity(opportunity_id, _user, service, goal_id)
