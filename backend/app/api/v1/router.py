"""API v1 aggregation."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.routes import auth, goals, health, opportunities, profile

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(profile.router)
api_router.include_router(goals.router)
api_router.include_router(opportunities.router)
