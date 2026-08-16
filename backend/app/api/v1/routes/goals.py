"""Objective management.

Goals are the unit an opportunity is scored against, so this is a load-bearing
endpoint rather than simple CRUD.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Query, status

from app.api.deps import CurrentUser, GoalServiceDep
from app.models.enums import GoalStatus
from app.schemas.goal import GoalCreate, GoalRead, GoalUpdate

router = APIRouter(prefix="/goals", tags=["goals"])


@router.get("", response_model=list[GoalRead], summary="List goals")
async def list_goals(
    user: CurrentUser,
    goals: GoalServiceDep,
    status_filter: GoalStatus | None = Query(default=None, alias="status"),
) -> list[GoalRead]:
    records = await goals.list_for_user(user.id, status_filter)
    return [GoalRead.model_validate(g) for g in records]


@router.post(
    "", response_model=GoalRead, status_code=status.HTTP_201_CREATED, summary="Create a goal"
)
async def create_goal(payload: GoalCreate, user: CurrentUser, goals: GoalServiceDep) -> GoalRead:
    goal = await goals.create(user.id, payload)
    return GoalRead.model_validate(goal)


@router.get("/{goal_id}", response_model=GoalRead, summary="Read a goal")
async def read_goal(goal_id: uuid.UUID, user: CurrentUser, goals: GoalServiceDep) -> GoalRead:
    goal = await goals.get(user.id, goal_id)
    return GoalRead.model_validate(goal)


@router.patch("/{goal_id}", response_model=GoalRead, summary="Update a goal")
async def update_goal(
    goal_id: uuid.UUID, payload: GoalUpdate, user: CurrentUser, goals: GoalServiceDep
) -> GoalRead:
    goal = await goals.update(user.id, goal_id, payload)
    return GoalRead.model_validate(goal)


@router.delete("/{goal_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a goal")
async def delete_goal(goal_id: uuid.UUID, user: CurrentUser, goals: GoalServiceDep) -> None:
    await goals.delete(user.id, goal_id)
