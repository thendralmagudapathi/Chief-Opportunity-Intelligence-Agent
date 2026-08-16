"""Agent card discovery endpoints."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_list_agent_cards(client) -> None:  # type: ignore[no-untyped-def]
    response = await client.get("/api/v1/agents")
    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) >= 8
    names = {item["name"] for item in items}
    assert "contrarian" in names
    assert "verification" in names


@pytest.mark.asyncio
async def test_get_agent_card(client) -> None:  # type: ignore[no-untyped-def]
    response = await client.get("/api/v1/agents/contrarian")
    assert response.status_code == 200
    assert response.json()["name"] == "contrarian"
