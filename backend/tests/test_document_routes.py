"""Document API routes."""

from __future__ import annotations

import io
import uuid

import pytest


@pytest.fixture
def storage_path(tmp_path, monkeypatch):  # type: ignore[no-untyped-def]
    monkeypatch.setenv("STORAGE__LOCAL_PATH", str(tmp_path / "uploads"))
    from app.core.config import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
async def client(app, storage_path):  # type: ignore[no-untyped-def]
    from httpx import ASGITransport, AsyncClient

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as http_client:
        yield http_client


async def test_upload_list_and_delete_document(client, registered_user, storage_path) -> None:  # type: ignore[no-untyped-def]
    from app.services.document_tasks import index_document_background

    files = {"file": ("resume.txt", io.BytesIO(b"PyTorch engineer in Bangalore"), "text/plain")}
    upload = await client.post(
        "/api/v1/documents",
        headers=registered_user["headers"],
        files=files,
    )
    assert upload.status_code == 202, upload.text
    document_id = upload.json()["document_id"]

    await index_document_background(uuid.UUID(document_id))

    listing = await client.get("/api/v1/documents", headers=registered_user["headers"])
    assert listing.status_code == 200
    assert any(item["id"] == document_id for item in listing.json()["items"])

    detail = await client.get(
        f"/api/v1/documents/{document_id}",
        headers=registered_user["headers"],
    )
    assert detail.status_code == 200
    assert detail.json()["status"] == "indexed"

    deleted = await client.delete(
        f"/api/v1/documents/{document_id}",
        headers=registered_user["headers"],
    )
    assert deleted.status_code == 204
