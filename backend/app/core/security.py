"""Security primitives: password hashing and JWT issuance/verification.

Argon2id via ``argon2-cffi`` and JWT via ``PyJWT`` — two small, audited
libraries instead of one large framework. Deliberately free of database and
HTTP concerns so it can be unit tested in isolation.
"""

from __future__ import annotations

import uuid
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from typing import Any, Literal

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.core.config import Settings, get_settings

TokenType = Literal["access", "refresh"]

# A tiny denylist of the passwords that dominate credential-stuffing lists.
# The real defence is the length requirement; this only stops the worst cases.
COMMON_PASSWORDS: frozenset[str] = frozenset(
    {
        "password",
        "password1",
        "password123",
        "passw0rd123",
        "123456789012",
        "qwertyuiop12",
        "letmein12345",
        "administrator",
        "iloveyou1234",
        "welcome12345",
        "changeme1234",
    }
)


@lru_cache
def _hasher() -> PasswordHasher:
    s = get_settings().security
    return PasswordHasher(
        time_cost=s.argon2_time_cost,
        memory_cost=s.argon2_memory_cost_kib,
        parallelism=s.argon2_parallelism,
    )


@lru_cache
def _dummy_hash() -> str:
    """Pre-computed hash used to equalise timing on unknown accounts."""
    return _hasher().hash("dummy-password-for-constant-time-comparison")


def hash_password(password: str) -> str:
    return _hasher().hash(password)


@dataclass(frozen=True, slots=True)
class PasswordCheck:
    ok: bool
    needs_rehash: bool = False


def verify_password(password: str, hashed: str | None) -> PasswordCheck:
    """Verify a password, spending the same work when the account is unknown.

    Passing ``None`` for ``hashed`` (unknown email) still performs a full
    verification against a dummy hash so response time does not disclose
    account existence.
    """
    hasher = _hasher()
    if hashed is None:
        with suppress(VerifyMismatchError, VerificationError, InvalidHashError):
            hasher.verify(_dummy_hash(), password)
        return PasswordCheck(ok=False)

    try:
        hasher.verify(hashed, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return PasswordCheck(ok=False)
    return PasswordCheck(ok=True, needs_rehash=hasher.check_needs_rehash(hashed))


def validate_password_policy(password: str, settings: Settings | None = None) -> list[str]:
    """Return a list of policy violations; empty means acceptable."""
    s = (settings or get_settings()).security
    problems: list[str] = []
    if len(password) < s.password_min_length:
        problems.append(f"must be at least {s.password_min_length} characters")
    if password.lower() in COMMON_PASSWORDS:
        problems.append("is too common")
    if password.strip() != password:
        problems.append("must not start or end with whitespace")
    return problems


@dataclass(frozen=True, slots=True)
class TokenPayload:
    subject: str
    token_type: TokenType
    jti: str
    issued_at: datetime
    expires_at: datetime


def _create_token(
    subject: str,
    token_type: TokenType,
    expires_delta: timedelta,
    settings: Settings | None = None,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    s = (settings or get_settings()).security
    now = datetime.now(UTC)
    claims: dict[str, Any] = {
        "sub": subject,
        "typ": token_type,
        "jti": uuid.uuid4().hex,
        "iat": int(now.timestamp()),
        "exp": int((now + expires_delta).timestamp()),
    }
    if extra_claims:
        claims.update(extra_claims)
    return jwt.encode(claims, s.secret_key.get_secret_value(), algorithm=s.jwt_algorithm)


def create_access_token(subject: str, settings: Settings | None = None) -> str:
    s = (settings or get_settings()).security
    return _create_token(subject, "access", timedelta(minutes=s.access_token_ttl_minutes), settings)


def create_refresh_token(subject: str, settings: Settings | None = None) -> str:
    s = (settings or get_settings()).security
    return _create_token(subject, "refresh", timedelta(days=s.refresh_token_ttl_days), settings)


class TokenError(Exception):
    """Raised for any invalid, expired or wrong-type token."""


def decode_token(
    token: str, expected_type: TokenType, settings: Settings | None = None
) -> TokenPayload:
    s = (settings or get_settings()).security
    try:
        claims = jwt.decode(
            token,
            s.secret_key.get_secret_value(),
            algorithms=[s.jwt_algorithm],
            options={"require": ["exp", "iat", "sub", "jti"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise TokenError("Token has expired") from exc
    except jwt.InvalidTokenError as exc:
        raise TokenError("Token is invalid") from exc

    # A refresh token must never be usable as an access token, and vice versa.
    if claims.get("typ") != expected_type:
        raise TokenError(f"Expected a {expected_type} token")

    return TokenPayload(
        subject=str(claims["sub"]),
        token_type=expected_type,
        jti=str(claims["jti"]),
        issued_at=datetime.fromtimestamp(claims["iat"], tz=UTC),
        expires_at=datetime.fromtimestamp(claims["exp"], tz=UTC),
    )
