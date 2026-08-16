"""Labelled duplicate set.

Each pair is ingested in isolation against an empty table (the session rolls
back afterwards). A pair labelled ``duplicate`` must be caught by one of the
cascade's first three probes; a pair labelled distinct must not. The gates in
``IMPLEMENTATION_PLAN.md`` are recall ≥ 0.95 and precision ≥ 0.98.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest
from app.models.enums import OpportunityCategory
from app.services.dedup import similarity, titles_compatible
from app.services.ingestion import IngestionOutcome, IngestionService, RawOpportunity


@dataclass(frozen=True)
class Pair:
    left: RawOpportunity
    right: RawOpportunity
    duplicate: bool
    method: str


def _raw(title: str, url: str, org: str, description: str = "Build things.") -> RawOpportunity:
    return RawOpportunity(
        title=title,
        source_url=url,
        category=OpportunityCategory.JOB,
        organization_name=org,
        description=description,
    )


PAIRS: tuple[Pair, ...] = (
    Pair(
        _raw("ML Engineer", "https://jobs.example.com/ml-engineer", "Acme"),
        _raw(
            "ML Engineer",
            "https://www.jobs.example.com/ml-engineer/?utm_source=twitter&utm_campaign=x",
            "Acme",
        ),
        True,
        "canonical_url",
    ),
    Pair(
        _raw("Research Scientist", "http://lab.example.org/rs", "Lab"),
        _raw("Research Scientist", "https://lab.example.org/rs/", "Lab"),
        True,
        "canonical_url",
    ),
    Pair(
        _raw("Grant call", "https://funders.example.org/a?b=2&a=1", "Fund"),
        _raw("Grant call", "https://funders.example.org/a?a=1&b=2#top", "Fund"),
        True,
        "canonical_url",
    ),
    Pair(
        _raw("Data Scientist", "https://employer.example.com/ds", "Employer", "Analyse data."),
        _raw("Data Scientist", "https://board.example.net/posting/42", "Employer", "Analyse data."),
        True,
        "content_hash",
    ),
    Pair(
        _raw("Fellow", "https://institute.example.edu/f1", "Institute", "A two-year fellowship."),
        _raw("Fellow", "https://aggregator.example.com/f1", "Institute", "A two-year fellowship."),
        True,
        "content_hash",
    ),
    Pair(
        _raw("Senior Machine Learning Engineer", "https://acme.example/a", "Acme Labs"),
        _raw("Machine Learning Engineer (Senior)", "https://acme.example/b", "Acme Labs"),
        True,
        "title_similarity",
    ),
    Pair(
        _raw("Research Scientist \u2013 Alignment", "https://lab.example/a", "Align Lab"),
        _raw("Research Scientist - Alignment", "https://lab.example/b", "Align Lab"),
        True,
        "title_similarity",
    ),
    Pair(
        _raw("  Staff  Engineer  ", "https://corp.example/a", "Corp"),
        _raw("Staff Engineer", "https://corp.example/b", "Corp"),
        True,
        "title_similarity",
    ),
    Pair(
        _raw("Postdoctoral Fellowship in Biology", "https://bio.example/a", "Bio Inst"),
        _raw("Postdoctoral Fellowship in Biology", "https://bio.example/b", "Bio Inst"),
        True,
        "title_similarity",
    ),
    Pair(
        _raw("Open Source Software Grant", "https://czi.example/a", "CZI"),
        _raw("Open Source Software Grant", "https://czi.example/b", "CZI"),
        True,
        "title_similarity",
    ),
    Pair(
        _raw("Senior Machine Learning Engineer", "https://acme2.example/a", "Acme Two"),
        _raw("Junior Machine Learning Engineer", "https://acme2.example/b", "Acme Two"),
        False,
        "seniority",
    ),
    Pair(
        _raw("Staff Scientist", "https://cernx.example/a", "Research Org"),
        _raw("Research Fellow", "https://cernx.example/b", "Research Org"),
        False,
        "seniority",
    ),
    Pair(
        _raw("Principal Engineer", "https://eng.example/a", "EngCo"),
        _raw("Engineer", "https://eng.example/b", "EngCo"),
        False,
        "seniority",
    ),
    Pair(
        _raw("Research Scientist", "https://org-a.example/rs", "Org A", "Work on models."),
        _raw("Research Scientist", "https://org-b.example/rs", "Org B", "Work on climate."),
        False,
        "different_org",
    ),
    Pair(
        _raw("Software Engineer", "https://start.example/se", "Startup", "Write software."),
        _raw(
            "Software Engineer",
            "https://bank.example/se",
            "Bank",
            "Write software for payments.",
        ),
        False,
        "different_org",
    ),
    Pair(
        _raw("ML Engineer", "https://shop.example/ml", "Shop"),
        _raw("Data Engineer", "https://shop.example/de", "Shop"),
        False,
        "different_role",
    ),
    Pair(
        _raw("Grant Manager", "https://fund.example/gm", "Funders"),
        _raw("Programme Officer", "https://fund.example/po", "Funders"),
        False,
        "different_role",
    ),
    Pair(
        _raw("PhD Student, Physics", "https://uni.example/phd", "University"),
        _raw("Faculty Position, Chemistry", "https://uni.example/fac", "University"),
        False,
        "different_role",
    ),
)


def test_seniority_veto_separates_junior_from_senior() -> None:
    assert titles_compatible("Senior Engineer", "Machine Learning Engineer (Senior)") is True
    assert titles_compatible("Senior Engineer", "Junior Engineer") is False
    assert similarity("Senior Machine Learning Engineer", "Junior Machine Learning Engineer") > 0.62


@pytest.fixture
async def session(database_url: str):  # type: ignore[no-untyped-def]
    from app.db.session import get_session_factory

    factory = get_session_factory()
    async with factory() as db:
        yield db
        await db.rollback()


async def test_labelled_duplicate_set_meets_gates(session) -> None:  # type: ignore[no-untyped-def]
    ingestion = IngestionService(session)
    true_positives = false_positives = false_negatives = 0

    for pair in PAIRS:
        first = await ingestion.ingest(pair.left)
        assert first.outcome is IngestionOutcome.CREATED, pair.method
        second = await ingestion.ingest(pair.right)
        detected = second.outcome in (
            IngestionOutcome.MERGED,
            IngestionOutcome.FLAGGED_DUPLICATE,
        )
        if pair.duplicate and detected:
            true_positives += 1
        elif pair.duplicate and not detected:
            false_negatives += 1
        elif not pair.duplicate and detected:
            false_positives += 1

        await session.rollback()

    labelled_positives = sum(1 for p in PAIRS if p.duplicate)
    detections = true_positives + false_positives
    recall = true_positives / labelled_positives
    precision = true_positives / detections if detections else 0.0
    assert recall >= 0.95, f"recall {recall:.3f} (FN={false_negatives})"
    assert precision >= 0.98, f"precision {precision:.3f} (FP={false_positives})"
