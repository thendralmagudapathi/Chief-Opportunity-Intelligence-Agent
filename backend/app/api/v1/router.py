"""API v1 aggregation."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.routes import (
    agent_runs,
    agents,
    auth,
    documents,
    evaluations,
    feedback,
    finetuning,
    goals,
    health,
    opportunities,
    outcomes,
    profile,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(profile.router)
api_router.include_router(documents.router)
api_router.include_router(goals.router)
api_router.include_router(opportunities.router)
api_router.include_router(agent_runs.router)
api_router.include_router(agents.router)
api_router.include_router(feedback.router)
api_router.include_router(outcomes.router)
api_router.include_router(evaluations.router)
api_router.include_router(finetuning.router)
