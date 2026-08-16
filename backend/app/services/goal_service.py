"""Goal CRUD.

Every query is scoped by ``user_id`` in SQL. A goal belonging to someone else is
reported as not found rather than forbidden, so the API does not disclose which
identifiers exist (docs/SECURITY_MODEL.md §4).
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.models.enums import GoalStatus
from app.models.goal import Goal
from app.schemas.goal import GoalCreate, GoalUpdate


class GoalService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_for_user(
        self, user_id: uuid.UUID, status: GoalStatus | None = None
    ) -> list[Goal]:
        stmt = select(Goal).where(Goal.user_id == user_id)
        if status is not None:
            stmt = stmt.where(Goal.status == status)
        stmt = stmt.order_by(Goal.priority.asc(), Goal.created_at.desc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get(self, user_id: uuid.UUID, goal_id: uuid.UUID) -> Goal:
        result = await self.session.execute(
            select(Goal).where(Goal.id == goal_id, Goal.user_id == user_id)
        )
        goal = result.scalar_one_or_none()
        if goal is None:
            raise NotFoundError("Goal not found")
        return goal

    async def create(self, user_id: uuid.UUID, data: GoalCreate) -> Goal:
        goal = Goal(
            user_id=user_id,
            title=data.title,
            description=data.description,
            objective_profile=data.objective_profile,
            priority=data.priority,
            deadline=data.deadline,
            desired_outcome=data.desired_outcome,
            constraints=data.constraints,
            acceptable_tradeoffs=data.acceptable_tradeoffs,
            weights_override=data.weights_override,
        )
        self.session.add(goal)
        await self.session.flush()
        return goal

    async def update(self, user_id: uuid.UUID, goal_id: uuid.UUID, data: GoalUpdate) -> Goal:
        goal = await self.get(user_id, goal_id)
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(goal, field, value)
        await self.session.flush()
        return goal

    async def delete(self, user_id: uuid.UUID, goal_id: uuid.UUID) -> None:
        goal = await self.get(user_id, goal_id)
        await self.session.delete(goal)
        await self.session.flush()
