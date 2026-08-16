"""Structured profile management."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import CurrentUser, RetrievalServiceDep, UserServiceDep
from app.schemas.profile import ProfilePatch, ProfileRead, ProfileUpdate
from app.schemas.retrieval import ProfileSearchRequest, ProfileSearchResponse, RetrievedPassage

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


@router.post("/search", response_model=ProfileSearchResponse, summary="Search the profile index")
async def search_profile(
    payload: ProfileSearchRequest,
    user: CurrentUser,
    retrieval: RetrievalServiceDep,
) -> ProfileSearchResponse:
    result = await retrieval.search_profile(
        user_id=user.id,
        query=payload.query,
        top_k=payload.top_k,
        rerank=payload.rerank,
    )
    return ProfileSearchResponse(
        query=result.query,
        degraded=result.degraded,
        detail=result.detail,
        passages=[
            RetrievedPassage(
                content=passage.content,
                score=passage.score,
                channel=passage.channel,
                chunk_id=passage.chunk_id,
                document_id=passage.document_id,
                meta=passage.meta,
            )
            for passage in result.passages
        ],
    )
