"""Scheduled intelligence digest generation."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.enums import GoalStatus, OpportunityEventType, OpportunityStatus
from app.models.goal import Goal
from app.models.opportunity import Opportunity, OpportunityEvent
from app.models.user import User

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class DigestItem:
    opportunity_id: uuid.UUID
    title: str
    category: str
    discovered_at: datetime


@dataclass(frozen=True, slots=True)
class UserDigest:
    user_id: uuid.UUID
    email: str
    goal_count: int
    new_opportunities: tuple[DigestItem, ...]


class ScheduledDigestService:
    """Summarise newly discovered opportunities for active users."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def build_digests(self, *, since_hours: int = 24) -> list[UserDigest]:
        since = datetime.now(UTC) - timedelta(hours=since_hours)
        users = list((await self.session.execute(select(User))).scalars())
        digests: list[UserDigest] = []
        for user in users:
            goals = list(
                (
                    await self.session.execute(
                        select(Goal).where(
                            Goal.user_id == user.id, Goal.status == GoalStatus.ACTIVE
                        )
                    )
                ).scalars()
            )
            if not goals:
                continue
            events = list(
                (
                    await self.session.execute(
                        select(OpportunityEvent, Opportunity)
                        .join(Opportunity, Opportunity.id == OpportunityEvent.opportunity_id)
                        .where(
                            OpportunityEvent.event_type == OpportunityEventType.DISCOVERED,
                            OpportunityEvent.created_at >= since,
                            Opportunity.status == OpportunityStatus.DISCOVERED,
                        )
                        .order_by(OpportunityEvent.created_at.desc())
                        .limit(20)
                    )
                ).all()
            )
            items = tuple(
                DigestItem(
                    opportunity_id=opportunity.id,
                    title=opportunity.title,
                    category=opportunity.category.value,
                    discovered_at=event.created_at,
                )
                for event, opportunity in events
            )
            if items:
                digests.append(
                    UserDigest(
                        user_id=user.id,
                        email=user.email,
                        goal_count=len(goals),
                        new_opportunities=items,
                    )
                )
        return digests

    async def emit(self, *, since_hours: int = 24) -> int:
        digests = await self.build_digests(since_hours=since_hours)
        for digest in digests:
            logger.info(
                "scheduled_digest",
                user_id=str(digest.user_id),
                email=digest.email,
                goal_count=digest.goal_count,
                new_count=len(digest.new_opportunities),
            )
        return len(digests)
