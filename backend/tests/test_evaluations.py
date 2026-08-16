"""Evaluation API routes."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_list_evaluations_empty(client, registered_user) -> None:  # type: ignore[no-untyped-def]
    response = await client.get("/api/v1/evaluations", headers=registered_user["headers"])
    assert response.status_code == 200
    assert response.json()["items"] == []
