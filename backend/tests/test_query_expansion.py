"""Query expansion tests."""

from __future__ import annotations

from app.agents.schemas import ObjectiveUnderstanding
from app.retrieval.expansion import expand_query


def test_expand_query_includes_original() -> None:
    variants = expand_query("climate grants", max_variants=3)
    assert variants[0] == "climate grants"


def test_expand_query_adds_keywords_and_countries() -> None:
    understanding = ObjectiveUnderstanding(
        intent="find roles",
        keywords=["python", "remote"],
        focus_countries=["DE"],
        success_criteria="good matches",
    )
    variants = expand_query("engineering roles", understanding, max_variants=4)
    assert len(variants) >= 2
    assert variants[0] == "engineering roles"
