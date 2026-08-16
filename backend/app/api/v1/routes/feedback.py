"""Feedback endpoints."""

from __future__ import annotations

from fastapi import APIRouter, status

from app.api.deps import CurrentUser, SessionDep
from app.schemas.feedback import FeedbackCreate, FeedbackRead
from app.services.feedback_service import FeedbackService

router = APIRouter(prefix="/feedback", tags=["feedback"])


@router.post("", response_model=FeedbackRead, status_code=status.HTTP_201_CREATED)
async def create_feedback(
    payload: FeedbackCreate,
    user: CurrentUser,
    session: SessionDep,
) -> FeedbackRead:
    row = await FeedbackService(session).create(user.id, payload)
    return FeedbackRead.model_validate(row)
