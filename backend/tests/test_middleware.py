"""Middleware behaviour: rate limiting, request identity and error shape."""

from __future__ import annotations

import pytest
from app.api.middleware import InMemoryRateLimiter
from app.core.config import get_settings
from app.main import create_app
from httpx import ASGITransport, AsyncClient


async def test_in_memory_limiter_opens_after_the_window() -> None:
    limiter = InMemoryRateLimiter()
    assert await limiter.hit("k", limit=2, window_s=60) == (True, 0)
    assert await limiter.hit("k", limit=2, window_s=60) == (True, 0)

    allowed, retry_after = await limiter.hit("k", limit=2, window_s=60)
    assert allowed is False
    assert retry_after > 0

    # A different key has its own budget.
    assert (await limiter.hit("other", limit=2, window_s=60))[0] is True


@pytest.fixture
async def strict_client(database_url: str):  # type: ignore[no-untyped-def]
    """An application whose auth bucket allows only two requests."""
    from app.db.session import dispose_engine

    settings = get_settings().model_copy(deep=True)
    settings.security.auth_rate_limit_requests = 2

    app = create_app(settings)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        yield client
    await dispose_engine()


async def test_auth_endpoints_are_rate_limited(strict_client) -> None:  # type: ignore[no-untyped-def]
    payload = {"email": "limited@example.com", "password": "a-long-enough-password-1"}

    for _ in range(2):
        response = await strict_client.post("/api/v1/auth/login", json=payload)
        assert response.status_code == 401  # rejected on credentials, not on rate

    limited = await strict_client.post("/api/v1/auth/login", json=payload)
    assert limited.status_code == 429
    assert limited.json()["type"] == "rate_limited"
    assert int(limited.headers["Retry-After"]) > 0


async def test_health_probes_bypass_the_rate_limit(strict_client) -> None:  # type: ignore[no-untyped-def]
    """An orchestrator's probes must never be throttled out of service."""
    for _ in range(10):
        assert (await strict_client.get("/api/v1/health/live")).status_code == 200


async def test_inbound_request_id_is_echoed_when_safe(client) -> None:  # type: ignore[no-untyped-def]
    response = await client.get("/api/v1/health/live", headers={"X-Request-ID": "abc123def456"})
    assert response.headers["X-Request-ID"] == "abc123def456"


async def test_hostile_request_id_is_replaced(client) -> None:  # type: ignore[no-untyped-def]
    response = await client.get(
        "/api/v1/health/live", headers={"X-Request-ID": "injected\nlog line"}
    )
    assert response.headers["X-Request-ID"] != "injected\nlog line"


async def test_unknown_route_uses_the_problem_shape(client) -> None:  # type: ignore[no-untyped-def]
    response = await client.get("/api/v1/does-not-exist")
    assert response.status_code == 404
    body = response.json()
    assert set(body) >= {"type", "title", "status", "detail", "instance", "trace_id"}
