"""Registration, login, refresh and identity."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, status

from app.api.deps import CurrentUser, SettingsDep, UserServiceDep
from app.core.errors import AuthenticationError
from app.core.security import (
    TokenError,
    create_access_token,
    create_refresh_token,
    decode_token,
)
from app.schemas.auth import (
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    TokenPair,
    UserRead,
)

router = APIRouter(prefix="/auth", tags=["auth"])


def _issue_tokens(subject: str, settings: SettingsDep) -> TokenPair:
    return TokenPair(
        access_token=create_access_token(subject, settings),
        refresh_token=create_refresh_token(subject, settings),
        expires_in=settings.security.access_token_ttl_minutes * 60,
    )


@router.post(
    "/register",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create an account",
)
async def register(payload: RegisterRequest, users: UserServiceDep) -> UserRead:
    user = await users.register(
        email=payload.email, password=payload.password, full_name=payload.full_name
    )
    return UserRead.model_validate(user)


@router.post("/login", response_model=TokenPair, summary="Exchange credentials for tokens")
async def login(payload: LoginRequest, users: UserServiceDep, settings: SettingsDep) -> TokenPair:
    user = await users.authenticate(payload.email, payload.password)
    return _issue_tokens(str(user.id), settings)


@router.post("/refresh", response_model=TokenPair, summary="Exchange a refresh token")
async def refresh(
    payload: RefreshRequest, users: UserServiceDep, settings: SettingsDep
) -> TokenPair:
    try:
        token = decode_token(payload.refresh_token, "refresh", settings)
        user_id = uuid.UUID(token.subject)
    except (TokenError, ValueError) as exc:
        raise AuthenticationError("Invalid or expired refresh token") from exc

    user = await users.get_by_id(user_id)
    if user is None or not user.is_active:
        raise AuthenticationError("Invalid or expired refresh token")
    return _issue_tokens(str(user.id), settings)


@router.get("/me", response_model=UserRead, summary="Current authenticated user")
async def me(user: CurrentUser) -> UserRead:
    return UserRead.model_validate(user)
