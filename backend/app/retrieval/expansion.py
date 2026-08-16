"""Deterministic query expansion for hybrid retrieval."""

from __future__ import annotations

from app.agents.schemas import ObjectiveUnderstanding


def expand_query(
    query: str,
    understanding: ObjectiveUnderstanding | None = None,
    *,
    max_variants: int = 3,
) -> list[str]:
    """Return deduplicated query variants, always including the original."""
    base = query.strip()
    if not base:
        return []

    variants: list[str] = [base]
    if understanding is None:
        return variants[:max_variants]

    for keyword in understanding.keywords:
        if len(variants) >= max_variants:
            break
        variant = f"{base} {keyword}".strip()
        if variant.casefold() not in {item.casefold() for item in variants}:
            variants.append(variant)

    for country in understanding.focus_countries:
        if len(variants) >= max_variants:
            break
        variant = f"{base} {country}".strip()
        if variant.casefold() not in {item.casefold() for item in variants}:
            variants.append(variant)

    return variants[:max_variants]
