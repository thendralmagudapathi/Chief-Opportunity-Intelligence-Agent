"""Hybrid fusion."""

from __future__ import annotations

import uuid

from app.retrieval.hybrid import reciprocal_rank_fusion
from app.retrieval.protocols import ScoredPassage


def test_rrf_promotes_items_present_in_both_lists() -> None:
    shared_id = uuid.uuid4()
    dense = [
        ScoredPassage(
            chunk_id=shared_id,
            content="shared passage",
            score=0.9,
            channel="dense",
        )
    ]
    lexical = [
        ScoredPassage(
            chunk_id=shared_id,
            content="shared passage",
            score=0.8,
            channel="lexical",
        ),
        ScoredPassage(
            chunk_id=uuid.uuid4(),
            content="lexical only",
            score=0.7,
            channel="lexical",
        ),
    ]
    fused = reciprocal_rank_fusion(dense, lexical, limit=2)
    assert fused[0].chunk_id == shared_id
    assert fused[0].channel == "fused"
