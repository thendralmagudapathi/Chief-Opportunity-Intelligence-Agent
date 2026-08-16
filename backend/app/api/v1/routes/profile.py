"""Structured profile management."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import CurrentUser, UserServiceDep
from app.schemas.profile import ProfilePatch, ProfileRead, ProfileUpdate

router = APIRouter(prefix="/profile", tags=["profile"])


@router.get("", response_model=ProfileRead, summary="Read the current user's profile")
async def read_profile(user: CurrentUser, users: UserServiceDep) -> ProfileRead:
    profile = await users.get_profile(user.id)
    return ProfileRead.model_validate(profile)


@router.put("", response_model=ProfileRead, summary="Replace the profile")
async def replace_profile(
    payload: ProfileUpdate, user: CurrentUser, users: UserServiceDep
) -> ProfileRead:
    profile = await users.replace_profile(user.id, payload)
    return ProfileRead.model_validate(profile)


@router.patch("", response_model=ProfileRead, summary="Partially update the profile")
async def patch_profile(
    payload: ProfilePatch, user: CurrentUser, users: UserServiceDep
) -> ProfileRead:
    profile = await users.patch_profile(user.id, payload)
    return ProfileRead.model_validate(profile)
