"""Opportunity read path: filtering, ordering and keyset pagination.

Rows are inserted directly rather than through a discovery pipeline, because the
pipeline is Phase 2 and this test is about the query layer.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from app.core.errors import ValidationError
from app.models.enums import OpportunityCategory, OpportunityStatus, RemoteStatus
from app.models.opportunity import Opportunity
from app.schemas.opportunity import OpportunityFilters
from app.services.opportunity_service import Cursor, OpportunityService

NOW = datetime.now(UTC)


def _opportunity(title: str, **overrides) -> Opportunity:  # type: ignore[no-untyped-def]
    values = {
        "title": title,
        "category": OpportunityCategory.JOB,
        "source_url": f"https://example.com/{uuid.uuid4().hex[:8]}",
        "status": OpportunityStatus.DISCOVERED,
        "remote_status": RemoteStatus.REMOTE,
        "requirements": [],
        "eligibility": {},
        "required_skills": [],
        "preferred_skills": [],
    }
    values.update(overrides)
    return Opportunity(**values)


@pytest.fixture
async def session(database_url: str):  # type: ignore[no-untyped-def]
    from app.db.session import get_session_factory

    factory = get_session_factory()
    async with factory() as db:
        yield db
        await db.rollback()


async def test_cursor_round_trip() -> None:
    row_id = uuid.uuid4()
    encoded = Cursor(value="42.5", row_id=row_id).encode()
    decoded = Cursor.decode(encoded)
    assert decoded.value == "42.5"
    assert decoded.row_id == row_id


async def test_malformed_cursor_is_a_validation_error() -> None:
    with pytest.raises(ValidationError):
        Cursor.decode("!!!not-base64!!!")


async def test_filters_and_pagination(session) -> None:  # type: ignore[no-untyped-def]
    service = OpportunityService(session)

    for index in range(5):
        session.add(
            _opportunity(
                f"Remote AI role {index}",
                location_country="DE",
                deadline=NOW + timedelta(days=index + 1),
            )
        )
    session.add(
        _opportunity(
            "Onsite role in India", location_country="IN", remote_status=RemoteStatus.ONSITE
        )
    )
    session.add(
        _opportunity(
            "Expired grant",
            category=OpportunityCategory.GRANT,
            status=OpportunityStatus.EXPIRED,
        )
    )
    await session.flush()

    everything = await service.list_opportunities(OpportunityFilters(), limit=50, sort="recent")
    titles = {row.opportunity.title for row in everything.rows}
    assert "Expired grant" not in titles, "expired opportunities must not be recommended"
    assert len(everything.rows) == 6

    with_expired = await service.list_opportunities(
        OpportunityFilters(include_expired=True), limit=50, sort="recent"
    )
    assert len(with_expired.rows) == 7

    german = await service.list_opportunities(
        OpportunityFilters(country="DE"), limit=50, sort="recent"
    )
    assert len(german.rows) == 5

    remote = await service.list_opportunities(
        OpportunityFilters(remote_status=RemoteStatus.ONSITE), limit=50, sort="recent"
    )
    assert [row.opportunity.title for row in remote.rows] == ["Onsite role in India"]

    searched = await service.list_opportunities(
        OpportunityFilters(q="Onsite"), limit=50, sort="recent"
    )
    assert len(searched.rows) == 1

    grants = await service.list_opportunities(
        OpportunityFilters(category=OpportunityCategory.GRANT, include_expired=True),
        limit=50,
        sort="recent",
    )
    assert len(grants.rows) == 1


async def test_keyset_pagination_visits_every_row_once(session) -> None:  # type: ignore[no-untyped-def]
    service = OpportunityService(session)
    for index in range(7):
        session.add(_opportunity(f"Paged opportunity {index}"))
    await session.flush()

    seen: list[uuid.UUID] = []
    cursor: str | None = None
    for _ in range(10):
        page = await service.list_opportunities(
            OpportunityFilters(), limit=3, cursor=cursor, sort="recent"
        )
        seen.extend(row.opportunity.id for row in page.rows)
        cursor = page.next_cursor
        if not page.has_more:
            break

    assert len(seen) == 7
    assert len(set(seen)) == 7, "keyset pagination returned a duplicate row"


async def test_deadline_sort_places_undated_last(session) -> None:  # type: ignore[no-untyped-def]
    service = OpportunityService(session)
    session.add(_opportunity("No deadline"))
    session.add(_opportunity("Soon", deadline=NOW + timedelta(days=1)))
    session.add(_opportunity("Later", deadline=NOW + timedelta(days=30)))
    await session.flush()

    page = await service.list_opportunities(OpportunityFilters(), limit=10, sort="deadline")
    assert [row.opportunity.title for row in page.rows] == ["Soon", "Later", "No deadline"]


async def test_missing_opportunity_raises_not_found(session) -> None:  # type: ignore[no-untyped-def]
    from app.core.errors import NotFoundError

    service = OpportunityService(session)
    with pytest.raises(NotFoundError):
        await service.get_opportunity(uuid.uuid4())
