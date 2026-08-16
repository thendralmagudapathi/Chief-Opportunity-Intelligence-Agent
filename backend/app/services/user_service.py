"""User registration, authentication and profile access.

Services own business rules and queries; they never commit. The request-scoped
session dependency owns the transaction boundary, so a handler that raises after
a service call leaves nothing half-written.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AuthenticationError, ConflictError, NotFoundError
from app.core.logging import get_logger
from app.core.security import hash_password, verify_password
from app.models.user import User, UserProfile
from app.schemas.profile import ProfilePatch, ProfileUpdate

logger = get_logger(__name__)

#: Profile fields persisted as JSON documents rather than typed columns.
PROFILE_JSON_SECTIONS = frozenset(
    {
        "skills",
        "work_authorization",
        "education",
        "certifications",
        "languages",
        "interests",
        "preferences",
        "constraints",
    }
)


class UserService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # -- accounts ---------------------------------------------------------

    async def get_by_id(self, user_id: uuid.UUID) -> User | None:
        return await self.session.get(User, user_id)

    async def get_by_email(self, email: str) -> User | None:
        result = await self.session.execute(select(User).where(User.email == email.lower()))
        return result.scalar_one_or_none()

    async def register(self, email: str, password: str, full_name: str | None) -> User:
        user = User(
            email=email.lower(),
            hashed_password=hash_password(password),
            full_name=full_name,
        )
        self.session.add(user)
        try:
            await self.session.flush()
        except IntegrityError as exc:
            await self.session.rollback()
            # Deliberately the same message the API would give for any conflict;
            # enumeration is prevented at the route by returning this only on
            # an authenticated-free path with a rate limit applied.
            raise ConflictError("An account with that email already exists") from exc

        self.session.add(UserProfile(user_id=user.id))
        await self.session.flush()
        logger.info("user_registered", user_id=str(user.id))
        return user

    async def authenticate(self, email: str, password: str) -> User:
        user = await self.get_by_email(email)
        check = verify_password(password, user.hashed_password if user else None)

        if user is None or not check.ok:
            logger.info("authentication_failed", email_domain=email.rpartition("@")[2])
            raise AuthenticationError("Invalid email or password")
        if not user.is_active:
            raise AuthenticationError("Account is disabled")

        if check.needs_rehash:
            user.hashed_password = hash_password(password)
        user.last_login_at = datetime.now(UTC)
        await self.session.flush()
        return user

    # -- profile ----------------------------------------------------------

    async def get_profile(self, user_id: uuid.UUID) -> UserProfile:
        """Return the profile, creating an empty one on first access."""
        result = await self.session.execute(
            select(UserProfile).where(UserProfile.user_id == user_id)
        )
        profile = result.scalar_one_or_none()
        if profile is None:
            profile = UserProfile(user_id=user_id)
            self.session.add(profile)
            await self.session.flush()
        return profile

    async def _apply_profile(
        self, profile: UserProfile, data: ProfileUpdate | ProfilePatch, *, partial: bool
    ) -> UserProfile:
        # Typed columns (Decimal, str) need Python values; JSONB sections need
        # JSON-safe values, so both dumps are taken and picked from per field.
        native = data.model_dump(exclude_unset=partial)
        jsonable = data.model_dump(mode="json", exclude_unset=partial)
        for field in native:
            value = jsonable[field] if field in PROFILE_JSON_SECTIONS else native[field]
            setattr(profile, field, value)
        await self.session.flush()
        return profile

    async def replace_profile(self, user_id: uuid.UUID, data: ProfileUpdate) -> UserProfile:
        profile = await self.get_profile(user_id)
        return await self._apply_profile(profile, data, partial=False)

    async def patch_profile(self, user_id: uuid.UUID, data: ProfilePatch) -> UserProfile:
        profile = await self.get_profile(user_id)
        return await self._apply_profile(profile, data, partial=True)

    async def require_user(self, user_id: uuid.UUID) -> User:
        user = await self.get_by_id(user_id)
        if user is None:
            raise NotFoundError("User not found")
        return user
