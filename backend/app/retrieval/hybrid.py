"""Hybrid search helpers."""

from __future__ import annotations

from app.retrieval.protocols import ScoredPassage

RRF_K = 60


def reciprocal_rank_fusion(
    *ranked_lists: list[ScoredPassage],
    limit: int,
) -> list[ScoredPassage]:
    """Fuse multiple ranked lists with reciprocal rank fusion."""
    scores: dict[str, float] = {}
    passages: dict[str, ScoredPassage] = {}

    for ranked in ranked_lists:
        for rank, passage in enumerate(ranked, start=1):
            key = _passage_key(passage)
            scores[key] = scores.get(key, 0.0) + 1.0 / (RRF_K + rank)
            passages[key] = passage

    fused = sorted(scores.items(), key=lambda item: item[1], reverse=True)[:limit]
    return [
        ScoredPassage(
            chunk_id=passages[key].chunk_id,
            content=passages[key].content,
            score=score,
            channel="fused",
            document_id=passages[key].document_id,
            meta={**passages[key].meta, "rrf": score},
        )
        for key, score in fused
    ]


def _passage_key(passage: ScoredPassage) -> str:
    if passage.chunk_id is not None:
        return str(passage.chunk_id)
    return f"profile:{hash(passage.content)}"
