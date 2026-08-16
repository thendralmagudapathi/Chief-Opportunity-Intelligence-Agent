"""Structured profile passages for hybrid retrieval."""

from __future__ import annotations

from decimal import Decimal

from app.models.user import UserProfile
from app.retrieval.protocols import ScoredPassage


def profile_passages(profile: UserProfile) -> list[ScoredPassage]:
    """Turn structured profile fields into searchable passages."""
    passages: list[ScoredPassage] = []

    def add(content: str, *, section: str) -> None:
        text = content.strip()
        if text:
            passages.append(
                ScoredPassage(
                    chunk_id=None,
                    content=text,
                    score=0.0,
                    channel="profile",
                    meta={"section": section},
                )
            )

    if profile.headline:
        add(profile.headline, section="headline")
    if profile.summary:
        add(profile.summary, section="summary")

    location_parts = [part for part in (profile.location_city, profile.location_country) if part]
    if location_parts:
        add("Location: " + ", ".join(location_parts), section="location")

    if profile.years_experience is not None:
        add(f"Years of experience: {profile.years_experience}", section="experience")

    for skill in profile.skills or []:
        name = skill.get("name") if isinstance(skill, dict) else None
        if name:
            level = skill.get("level")
            years = skill.get("years")
            detail = f"Skill: {name}"
            if level is not None:
                detail += f" (level {level})"
            if years is not None:
                detail += f", {years} years"
            add(detail, section="skills")

    for item in profile.education or []:
        if isinstance(item, dict) and item.get("institution"):
            parts = [str(item["institution"])]
            if item.get("degree"):
                parts.append(str(item["degree"]))
            if item.get("field_of_study"):
                parts.append(str(item["field_of_study"]))
            add("Education: " + ", ".join(parts), section="education")

    for item in profile.certifications or []:
        if isinstance(item, dict) and item.get("name"):
            add(f"Certification: {item['name']}", section="certifications")

    for item in profile.work_authorization or []:
        if isinstance(item, dict) and item.get("country"):
            status = item.get("status", "unknown")
            add(f"Work authorization ({item['country']}): {status}", section="work_authorization")

    salary_min = _decimal_text(profile.salary_expectation_min)
    salary_max = _decimal_text(profile.salary_expectation_max)
    if salary_min or salary_max:
        currency = profile.salary_currency or ""
        add(
            f"Salary expectation: {salary_min or '?'} - {salary_max or '?'} {currency}".strip(),
            section="salary",
        )

    for interest in profile.interests or []:
        if isinstance(interest, str) and interest.strip():
            add(f"Interest: {interest.strip()}", section="interests")

    return passages


def rank_profile_passages(
    query: str, passages: list[ScoredPassage], *, limit: int
) -> list[ScoredPassage]:
    tokens = {token for token in query.lower().split() if token}
    if not tokens:
        return passages[:limit]

    scored: list[ScoredPassage] = []
    for passage in passages:
        content = passage.content.lower()
        hits = sum(1 for token in tokens if token in content)
        if hits:
            scored.append(
                ScoredPassage(
                    chunk_id=passage.chunk_id,
                    content=passage.content,
                    score=hits / len(tokens),
                    channel="profile",
                    document_id=passage.document_id,
                    meta=passage.meta,
                )
            )
    scored.sort(key=lambda item: item.score, reverse=True)
    return scored[:limit]


def _decimal_text(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return format(value, "f")
