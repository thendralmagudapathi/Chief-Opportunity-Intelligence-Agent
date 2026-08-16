"""Test fixtures.

The suite runs against a SQLite database created by the *real* Alembic
migration, not by ``metadata.create_all``. That is deliberate: it means the
migration itself is exercised on every test run, so schema drift is caught
immediately rather than at deployment time.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]

# Settings are read (and cached) the first time application code is imported,
# so the environment must be configured before any app import happens.
os.environ.update(
    {
        "ENVIRONMENT": "test",
        "DEBUG": "false",
        "SECURITY__SECRET_KEY": "test-secret-key-not-used-outside-the-test-suite",
        # Argon2 tuned down: the default profile costs ~100 ms per hash, which
        # would dominate the runtime of an otherwise fast suite.
        "SECURITY__ARGON2_TIME_COST": "1",
        "SECURITY__ARGON2_MEMORY_COST_KIB": "8192",
        "SECURITY__ARGON2_PARALLELISM": "1",
        "SECURITY__AUTH_RATE_LIMIT_REQUESTS": "500",
        "SECURITY__RATE_LIMIT_REQUESTS": "5000",
        "REDIS__ENABLED": "false",
        "RAG__EMBEDDING_PROVIDER": "fake",
        "RAG__RERANK_ENABLED": "true",
        "MODELS__PROVIDER": "fake",
        "OBSERVABILITY__LOG_LEVEL": "WARNING",
    }
)


@pytest.fixture(scope="session")
def database_url(tmp_path_factory: pytest.TempPathFactory) -> Iterator[str]:
    """Create a migrated SQLite database for the whole session."""
    from alembic import command
    from alembic.config import Config
    from app.core.config import get_settings

    db_path = tmp_path_factory.mktemp("db") / "test.db"
    url = f"sqlite+aiosqlite:///{db_path.as_posix()}"
    os.environ["DATABASE__URL"] = url
    get_settings.cache_clear()

    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "app" / "db" / "migrations"))
    command.upgrade(config, "head")

    yield url

    get_settings.cache_clear()


@pytest.fixture
def settings(database_url: str):  # type: ignore[no-untyped-def]
    from app.core.config import get_settings

    return get_settings()


@pytest.fixture
async def app(database_url: str) -> AsyncIterator[object]:
    """A fresh application per test.

    Fresh because the in-memory rate limiter lives on the middleware instance;
    reusing one app would leak request counts between tests.
    """
    from app.core.config import get_settings
    from app.db.session import dispose_engine
    from app.main import create_app

    application = create_app(get_settings())
    yield application
    await dispose_engine()


@pytest.fixture
async def client(app):  # type: ignore[no-untyped-def]
    from httpx import ASGITransport, AsyncClient

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as http_client:
        yield http_client


@pytest.fixture
async def registered_user(client):  # type: ignore[no-untyped-def]
    """Register a unique user and return its credentials plus an access token."""
    import uuid

    email = f"user-{uuid.uuid4().hex[:12]}@example.com"
    password = "correct-horse-battery-staple"

    response = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "full_name": "Test User"},
    )
    assert response.status_code == 201, response.text
    user = response.json()

    login = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert login.status_code == 200, login.text
    tokens = login.json()

    return {
        "id": user["id"],
        "email": email,
        "password": password,
        "access_token": tokens["access_token"],
        "refresh_token": tokens["refresh_token"],
        "headers": {"Authorization": f"Bearer {tokens['access_token']}"},
    }


@pytest.fixture
async def admin_user(client, registered_user):  # type: ignore[no-untyped-def]
    """Registered user promoted to superuser for admin-only routes."""
    import uuid

    from app.db.session import get_session_factory
    from app.models.user import User

    factory = get_session_factory()
    async with factory() as session:
        user = await session.get(User, uuid.UUID(registered_user["id"]))
        assert user is not None
        user.is_superuser = True
        await session.commit()
    return registered_user


@pytest.fixture
async def cleanup_opportunities():  # type: ignore[no-untyped-def]
    """Delete opportunity rows tests commit into the session-scoped database."""
    import uuid

    from app.db.session import get_session_factory
    from app.models.opportunity import Opportunity
    from sqlalchemy import delete

    created: list[uuid.UUID] = []
    yield created

    factory = get_session_factory()
    async with factory() as session:
        await session.execute(delete(Opportunity).where(Opportunity.id.in_(created)))
        await session.commit()
