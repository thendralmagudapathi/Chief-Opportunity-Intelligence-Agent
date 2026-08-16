"""End-to-end smoke test.

Exercises the full Phase 1 path against a migrated database: health, register,
login, identity, refresh, profile write/read, goal CRUD and the opportunity
list. If this passes, the foundation genuinely runs end to end.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.smoke


async def test_health_endpoints(client) -> None:  # type: ignore[no-untyped-def]
    live = await client.get("/api/v1/health/live")
    assert live.status_code == 200
    assert live.json()["status"] == "ok"

    ready = await client.get("/api/v1/health/ready")
    assert ready.status_code == 200, ready.text
    body = ready.json()
    assert body["status"] == "ok"
    assert any(check["name"] == "database" and check["status"] == "ok" for check in body["checks"])

    info = await client.get("/api/v1/health/info")
    assert info.status_code == 200
    assert info.json()["environment"] == "test"


async def test_request_id_header_is_returned(client) -> None:  # type: ignore[no-untyped-def]
    response = await client.get("/api/v1/health/live")
    assert response.headers["X-Request-ID"]
    assert response.headers["X-Content-Type-Options"] == "nosniff"


async def test_full_user_journey(client, registered_user) -> None:  # type: ignore[no-untyped-def]
    headers = registered_user["headers"]

    me = await client.get("/api/v1/auth/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["email"] == registered_user["email"]

    refreshed = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": registered_user["refresh_token"]}
    )
    assert refreshed.status_code == 200
    assert refreshed.json()["access_token"]

    # Profile is created empty on first read, then patched.
    profile = await client.get("/api/v1/profile", headers=headers)
    assert profile.status_code == 200
    assert profile.json()["skills"] == []

    patched = await client.patch(
        "/api/v1/profile",
        headers=headers,
        json={
            "headline": "AI engineer",
            "location_country": "in",
            "years_experience": 4.5,
            "skills": [{"name": "PyTorch", "level": 4, "years": 3}],
            "work_authorization": [
                {"country": "de", "status": "none", "requires_sponsorship": True}
            ],
        },
    )
    assert patched.status_code == 200, patched.text
    body = patched.json()
    assert body["headline"] == "AI engineer"
    assert body["location_country"] == "IN"  # normalised to upper case
    assert body["skills"][0]["name"] == "PyTorch"
    assert body["work_authorization"][0]["country"] == "DE"

    # The patch must not have wiped untouched sections.
    reread = await client.get("/api/v1/profile", headers=headers)
    assert reread.json()["skills"][0]["level"] == 4

    goal = await client.post(
        "/api/v1/goals",
        headers=headers,
        json={
            "title": "Move to Germany and secure an AI engineering role",
            "objective_profile": "career",
            "priority": 1,
            "desired_outcome": "Signed offer with relocation support",
            "constraints": {"min_salary_eur": 75000, "requires_visa_sponsorship": True},
            "acceptable_tradeoffs": ["smaller company"],
        },
    )
    assert goal.status_code == 201, goal.text
    goal_id = goal.json()["id"]
    assert goal.json()["status"] == "active"

    listed = await client.get("/api/v1/goals", headers=headers)
    assert listed.status_code == 200
    assert [g["id"] for g in listed.json()] == [goal_id]

    updated = await client.patch(
        f"/api/v1/goals/{goal_id}", headers=headers, json={"priority": 2, "status": "paused"}
    )
    assert updated.status_code == 200
    assert updated.json()["priority"] == 2
    assert updated.json()["status"] == "paused"

    filtered = await client.get("/api/v1/goals?status=active", headers=headers)
    assert filtered.json() == []

    opportunities = await client.get("/api/v1/opportunities", headers=headers)
    assert opportunities.status_code == 200
    page = opportunities.json()
    assert page["items"] == []
    assert page["has_more"] is False
    assert page["next_cursor"] is None

    deleted = await client.delete(f"/api/v1/goals/{goal_id}", headers=headers)
    assert deleted.status_code == 204
    assert (await client.get(f"/api/v1/goals/{goal_id}", headers=headers)).status_code == 404
