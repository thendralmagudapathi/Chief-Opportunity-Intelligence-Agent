"""FastAPI dependencies: settings, database session, authenticated principal."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.errors import AuthenticationError, PermissionDeniedError
from app.core.security import TokenError, decode_token
from app.db.session import get_db_session
from app.models.user import User
from app.services.goal_service import GoalService
from app.services.ingestion import IngestionService
from app.services.opportunity_service import OpportunityService
from app.services.scoring_service import ScoringService
from app.services.user_service import UserService

# auto_error=False so a missing header raises our own error contract rather
# than Starlette's default JSON body.
bearer_scheme = HTTPBearer(auto_error=False, description="JWT access token")

SettingsDep = Annotated[Settings, Depends(get_settings)]
SessionDep = Annotated[AsyncSession, Depends(get_db_session)]


def get_user_service(session: SessionDep) -> UserService:
    return UserService(session)


def get_goal_service(session: SessionDep) -> GoalService:
    return GoalService(session)


def get_opportunity_service(session: SessionDep) -> OpportunityService:
    return OpportunityService(session)


def get_ingestion_service(session: SessionDep) -> IngestionService:
    return IngestionService(session)


def get_scoring_service(session: SessionDep) -> ScoringService:
    return ScoringService(session)


UserServiceDep = Annotated[UserService, Depends(get_user_service)]
GoalServiceDep = Annotated[GoalService, Depends(get_goal_service)]
OpportunityServiceDep = Annotated[OpportunityService, Depends(get_opportunity_service)]
IngestionServiceDep = Annotated[IngestionService, Depends(get_ingestion_service)]
ScoringServiceDep = Annotated[ScoringService, Depends(get_scoring_service)]


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    users: UserServiceDep,
    settings: SettingsDep,
) -> User:
    if credentials is None or not credentials.credentials:
        raise AuthenticationError("Missing bearer token")

    try:
        payload = decode_token(credentials.credentials, "access", settings)
        user_id = uuid.UUID(payload.subject)
    except (TokenError, ValueError) as exc:
        raise AuthenticationError("Invalid or expired token") from exc

    user = await users.get_by_id(user_id)
    if user is None or not user.is_active:
        # A deactivated or deleted account must not keep working until its token
        # expires, so activity is checked on every request rather than at login.
        raise AuthenticationError("Invalid or expired token")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


async def get_current_superuser(user: CurrentUser) -> User:
    if not user.is_superuser:
        raise PermissionDeniedError("Administrator privileges required")
    return user


CurrentSuperuser = Annotated[User, Depends(get_current_superuser)]
