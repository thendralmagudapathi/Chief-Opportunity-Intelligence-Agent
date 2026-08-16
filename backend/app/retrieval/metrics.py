"""Retrieval evaluation metrics."""

from __future__ import annotations

import math


def recall_at_k(relevant: set[str], retrieved: list[str], k: int) -> float:
    if not relevant:
        return 0.0
    hits = sum(1 for item in retrieved[:k] if item in relevant)
    return hits / len(relevant)


def phrase_recall_at_k(relevant_phrases: set[str], retrieved: list[str], k: int) -> float:
    """Fraction of phrases found inside at least one retrieved passage."""
    if not relevant_phrases:
        return 0.0
    hits = sum(
        1
        for phrase in relevant_phrases
        if any(phrase in passage for passage in retrieved[:k])
    )
    return hits / len(relevant_phrases)


def ndcg_at_k(relevant: set[str], retrieved: list[str], k: int) -> float:
    if not relevant:
        return 0.0
    dcg = sum(
        1.0 / math.log2(rank + 2) for rank, item in enumerate(retrieved[:k]) if item in relevant
    )
    ideal_hits = min(len(relevant), k)
    idcg = sum(1.0 / math.log2(rank + 2) for rank in range(ideal_hits))
    if idcg == 0:
        return 0.0
    return dcg / idcg


def phrase_ndcg_at_k(relevant_phrases: set[str], retrieved: list[str], k: int) -> float:
    """NDCG when relevance means a phrase appears inside a retrieved passage."""
    if not relevant_phrases:
        return 0.0
    gains: list[float] = []
    for rank, passage in enumerate(retrieved[:k]):
        if any(phrase in passage for phrase in relevant_phrases):
            gains.append(1.0 / math.log2(rank + 2))
    dcg = sum(gains)
    ideal = min(len(relevant_phrases), k)
    idcg = sum(1.0 / math.log2(rank + 2) for rank in range(ideal))
    if idcg == 0:
        return 0.0
    return dcg / idcg
