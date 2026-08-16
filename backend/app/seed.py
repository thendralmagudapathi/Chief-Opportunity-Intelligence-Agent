"""Load the fixture corpus through the real ingestion pipeline.

Usage::

    cd backend && python -m app.seed
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.data.corpus import CORPUS, SOURCES
from app.models.enums import OpportunityCategory, RemoteStatus, SourceType
from app.models.opportunity import OpportunitySource
from app.services.ingestion import IngestionReport, IngestionService, RawOpportunity

logger = get_logger(__name__)


async def upsert_sources(session: AsyncSession) -> dict[str, uuid.UUID]:
    """Ensure every configured source exists; return key → id."""
    existing = {
        row.key: row for row in (await session.execute(select(OpportunitySource))).scalars().all()
    }
    ids: dict[str, uuid.UUID] = {}
    for spec in SOURCES:
        row = existing.get(spec["key"])
        if row is None:
            row = OpportunitySource(
                key=spec["key"],
                name=spec["name"],
                source_type=SourceType(spec["source_type"]),
                base_url=spec.get("base_url"),
                robots_respected=spec.get("robots_respected", True),
            )
            session.add(row)
            await session.flush()
        ids[spec["key"]] = row.id
    return ids


def _to_raw(item: dict[str, Any]) -> RawOpportunity:
    remote = item["remote_status"]
    if not isinstance(remote, RemoteStatus):
        remote = RemoteStatus(remote) if remote else RemoteStatus.UNKNOWN
    category = item["category"]
    if not isinstance(category, OpportunityCategory):
        category = OpportunityCategory(category)
    return RawOpportunity(
        title=item["title"],
        source_url=item["source_url"],
        category=category,
        organization_name=item.get("organization_name"),
        summary=item.get("summary"),
        location_country=item.get("location_country"),
        remote_status=remote,
        required_skills=list(item.get("required_skills") or []),
        preferred_skills=list(item.get("preferred_skills") or []),
        compensation_min=item.get("compensation_min"),
        compensation_max=item.get("compensation_max"),
        compensation_currency=item.get("compensation_currency"),
        compensation_period=item.get("compensation_period"),
        deadline=item.get("deadline"),
    )


async def seed_corpus(session: AsyncSession, *, now: datetime | None = None) -> IngestionReport:
    """Insert sources and ingest the fixture corpus. Idempotent."""
    source_ids = await upsert_sources(session)
    ingestion = IngestionService(session)
    created = merged = flagged = rejected = 0
    for item in CORPUS:
        result = await ingestion.ingest(
            _to_raw(item),
            source_id=source_ids.get(item.get("source_key", "fixture")),
            now=now,
        )
        match result.outcome.value:
            case "created":
                created += 1
            case "merged":
                merged += 1
            case "flagged_duplicate":
                flagged += 1
            case "rejected":
                rejected += 1
                logger.info("seed_rejected", title=item["title"], reason=result.reason)
    return IngestionReport(created, merged, flagged, rejected)


async def _run() -> None:
    from app.core.config import get_settings
    from app.core.logging import configure_logging
    from app.db.session import dispose_engine, get_session_factory

    configure_logging(get_settings())
    factory = get_session_factory()
    async with factory() as session:
        report = await seed_corpus(session, now=datetime.now(UTC))
        await session.commit()
    await dispose_engine()
    logger.info(
        "seed_complete",
        created=report.created,
        merged=report.merged,
        flagged=report.flagged,
        rejected=report.rejected,
    )
    print(  # noqa: T201  (CLI summary for operators running the seed)
        f"seeded: created={report.created} merged={report.merged} "
        f"flagged={report.flagged} rejected={report.rejected}"
    )


if __name__ == "__main__":
    asyncio.run(_run())
