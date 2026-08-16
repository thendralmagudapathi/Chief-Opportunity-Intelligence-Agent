"""Append-only memory with provenance (Phase 6)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError, ValidationError
from app.models.enums import MemoryType
from app.models.memory import MemoryRecord


class MemoryService:
    """Memory writes never mutate an existing row in place."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def recall(
        self,
        user_id: uuid.UUID,
        memory_type: MemoryType,
        *,
        limit: int = 8,
    ) -> list[MemoryRecord]:
        stmt = (
            select(MemoryRecord)
            .where(
                MemoryRecord.user_id == user_id,
                MemoryRecord.memory_type == memory_type,
                MemoryRecord.valid_to.is_(None),
            )
            .order_by(MemoryRecord.created_at.desc())
            .limit(limit)
        )
        return list((await self.session.execute(stmt)).scalars())

    async def write_semantic(
        self,
        *,
        user_id: uuid.UUID,
        key: str,
        content: str,
        provenance: dict[str, Any],
        confidence: float | None = None,
    ) -> MemoryRecord:
        if not key.strip():
            raise ValidationError("Memory key is required")
        existing = await self._active_semantic(user_id, key)
        if existing is not None and existing.content == content:
            return existing

        record = MemoryRecord(
            user_id=user_id,
            memory_type=MemoryType.SEMANTIC,
            key=key.strip(),
            content=content,
            confidence=confidence,
            provenance=provenance,
            valid_from=datetime.now(UTC),
        )
        self.session.add(record)
        await self.session.flush()

        if existing is not None:
            await self._supersede(existing, record.id)
        return record

    async def write_episodic(
        self,
        *,
        user_id: uuid.UUID,
        content: str,
        provenance: dict[str, Any],
        source_ref: str | None = None,
        importance: float | None = None,
    ) -> MemoryRecord:
        record = MemoryRecord(
            user_id=user_id,
            memory_type=MemoryType.EPISODIC,
            content=content,
            provenance=provenance,
            source_ref=source_ref,
            importance=importance,
            valid_from=datetime.now(UTC),
        )
        self.session.add(record)
        await self.session.flush()
        return record

    async def write_outcome(
        self,
        *,
        user_id: uuid.UUID,
        content: str,
        provenance: dict[str, Any],
        source_ref: str | None = None,
        confidence: float | None = None,
    ) -> MemoryRecord:
        record = MemoryRecord(
            user_id=user_id,
            memory_type=MemoryType.OUTCOME,
            content=content,
            provenance=provenance,
            source_ref=source_ref,
            confidence=confidence,
            valid_from=datetime.now(UTC),
        )
        self.session.add(record)
        await self.session.flush()
        return record

    async def get_record(self, user_id: uuid.UUID, record_id: uuid.UUID) -> MemoryRecord:
        record = await self.session.get(MemoryRecord, record_id)
        if record is None or record.user_id != user_id:
            raise NotFoundError("Memory record not found")
        return record

    async def _active_semantic(self, user_id: uuid.UUID, key: str) -> MemoryRecord | None:
        stmt = (
            select(MemoryRecord)
            .where(
                MemoryRecord.user_id == user_id,
                MemoryRecord.memory_type == MemoryType.SEMANTIC,
                MemoryRecord.key == key,
                MemoryRecord.valid_to.is_(None),
            )
            .limit(1)
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def _supersede(self, existing: MemoryRecord, new_id: uuid.UUID) -> None:
        moment = datetime.now(UTC)
        existing.valid_to = moment
        existing.superseded_by_id = new_id
        await self.session.flush()
