"""Authentication and authorisation behaviour."""

from __future__ import annotations

import uuid


async def test_register_rejects_weak_password(client) -> None:  # type: ignore[no-untyped-def]
    response = await client.post(
        "/api/v1/auth/register", json={"email": "weak@example.com", "password": "short"}
    )
    assert response.status_code == 422
    assert response.json()["type"] == "validation_error"


async def test_register_rejects_common_password(client) -> None:  # type: ignore[no-untyped-def]
    response = await client.post(
        "/api/v1/auth/register", json={"email": "common@example.com", "password": "password123"}
    )
    assert response.status_code == 422


async def test_duplicate_registration_conflicts(client, registered_user) -> None:  # type: ignore[no-untyped-def]
    response = await client.post(
        "/api/v1/auth/register",
        json={"email": registered_user["email"], "password": "another-long-password-1"},
    )
    assert response.status_code == 409
    assert response.json()["type"] == "conflict"


async def test_login_failures_are_indistinguishable(client, registered_user) -> None:  # type: ignore[no-untyped-def]
    """Wrong password and unknown account must return the same thing."""
    wrong_password = await client.post(
        "/api/v1/auth/login",
        json={"email": registered_user["email"], "password": "definitely-not-the-password"},
    )
    unknown_user = await client.post(
        "/api/v1/auth/login",
        json={"email": f"nobody-{uuid.uuid4().hex[:8]}@example.com", "password": "irrelevant-pw-1"},
    )

    assert wrong_password.status_code == unknown_user.status_code == 401
    assert wrong_password.json()["detail"] == unknown_user.json()["detail"]


async def test_protected_route_requires_token(client) -> None:  # type: ignore[no-untyped-def]
    response = await client.get("/api/v1/auth/me")
    assert response.status_code == 401
    assert response.json()["type"] == "unauthenticated"


async def test_refresh_token_is_not_accepted_as_access_token(client, registered_user) -> None:  # type: ignore[no-untyped-def]
    """Token type confusion is the classic JWT mistake; ``typ`` prevents it."""
    response = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {registered_user['refresh_token']}"},
    )
    assert response.status_code == 401


async def test_garbage_token_is_rejected(client) -> None:  # type: ignore[no-untyped-def]
    response = await client.get("/api/v1/auth/me", headers={"Authorization": "Bearer not.a.jwt"})
    assert response.status_code == 401


async def test_goals_are_scoped_to_their_owner(client, registered_user) -> None:  # type: ignore[no-untyped-def]
    """Another user's goal must look like it does not exist, not like a 403."""
    created = await client.post(
        "/api/v1/goals",
        headers=registered_user["headers"],
        json={"title": "Private objective of the first user"},
    )
    goal_id = created.json()["id"]

    other_email = f"other-{uuid.uuid4().hex[:12]}@example.com"
    await client.post(
        "/api/v1/auth/register",
        json={"email": other_email, "password": "another-correct-horse-1"},
    )
    login = await client.post(
        "/api/v1/auth/login", json={"email": other_email, "password": "another-correct-horse-1"}
    )
    other_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    response = await client.get(f"/api/v1/goals/{goal_id}", headers=other_headers)
    assert response.status_code == 404
    assert (await client.get("/api/v1/goals", headers=other_headers)).json() == []
