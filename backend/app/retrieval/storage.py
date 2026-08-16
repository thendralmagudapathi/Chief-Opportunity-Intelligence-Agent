"""Local filesystem object storage for development."""

from __future__ import annotations

import asyncio
from pathlib import Path

from app.core.errors import NotFoundError


class LocalObjectStorage:
    def __init__(self, root: Path) -> None:
        self._root = root
        self._root.mkdir(parents=True, exist_ok=True)

    async def put(self, *, key: str, data: bytes, content_type: str) -> str:
        del content_type
        path = self._root / key
        path.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(path.write_bytes, data)
        return f"file://{path.as_posix()}"

    async def get(self, *, uri: str) -> bytes:
        path = _uri_to_path(uri, self._root)
        if not path.exists():
            raise NotFoundError("Stored document bytes not found")
        return await asyncio.to_thread(path.read_bytes)

    async def delete(self, *, uri: str) -> None:
        path = _uri_to_path(uri, self._root)
        if path.exists():
            await asyncio.to_thread(path.unlink)


def _uri_to_path(uri: str, root: Path) -> Path:
    if uri.startswith("file://"):
        return Path(uri.removeprefix("file://"))
    return root / uri
