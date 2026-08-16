"""Outcome tracking endpoints."""

from __future__ import annotations

from fastapi import APIRouter, status

from app.api.deps import CurrentUser, SessionDep
from app.schemas.outcome import OutcomeCreate, OutcomeRead
from app.services.outcome_service import OutcomeService

router = APIRouter(prefix="/outcomes", tags=["outcomes"])


@router.post("", response_model=OutcomeRead, status_code=status.HTTP_201_CREATED)
async def record_outcome(
    payload: OutcomeCreate,
    user: CurrentUser,
    session: SessionDep,
) -> OutcomeRead:
    row = await OutcomeService(session).record(user.id, payload)
    return OutcomeRead.model_validate(row)
