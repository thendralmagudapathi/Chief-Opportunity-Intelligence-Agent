"""Feedback and outcome endpoints."""

from __future__ import annotations

import uuid

import pytest


@pytest.mark.asyncio
async def test_create_feedback(client, registered_user) -> None:  # type: ignore[no-untyped-def]
    response = await client.post(
        "/api/v1/feedback",
        headers=registered_user["headers"],
        json={"signal": "relevant", "comment": "Useful match"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["signal"] == "relevant"
    assert body["user_id"] == registered_user["id"]


@pytest.mark.asyncio
async def test_record_outcome_requires_opportunity(
    client, registered_user, cleanup_opportunities
) -> None:  # type: ignore[no-untyped-def]
    missing = await client.post(
        "/api/v1/outcomes",
        headers=registered_user["headers"],
        json={"opportunity_id": str(uuid.uuid4()), "outcome": "ignored"},
    )
    assert missing.status_code == 404
