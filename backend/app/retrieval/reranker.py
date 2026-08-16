"""Cross-encoder and test rerankers."""

from __future__ import annotations

import re
from typing import Any

from app.retrieval.protocols import Reranker, ScoredPassage

_TOKEN = re.compile(r"[a-z0-9]+", re.IGNORECASE)


def _tokens(text: str) -> set[str]:
    return set(_TOKEN.findall(text.casefold()))


class FakeReranker:
    """Lexical overlap reranker for tests and offline runs."""

    async def rerank(
        self, query: str, passages: list[ScoredPassage], *, top_n: int
    ) -> list[ScoredPassage]:
        query_tokens = _tokens(query)
        scored: list[tuple[float, ScoredPassage]] = []
        for passage in passages:
            overlap = len(query_tokens & _tokens(passage.content))
            score = overlap / max(len(query_tokens), 1)
            scored.append(
                (
                    score,
                    ScoredPassage(
                        chunk_id=passage.chunk_id,
                        content=passage.content,
                        score=score,
                        channel="reranked",
                        document_id=passage.document_id,
                        meta={**passage.meta, "rerank_score": score},
                    ),
                )
            )
        scored.sort(key=lambda item: item[0], reverse=True)
        return [item[1] for item in scored[:top_n]]


class CrossEncoderReranker:
    """Sentence-transformers cross-encoder reranking."""

    def __init__(self, model_name: str) -> None:
        self._model_name = model_name
        self._model: Any | None = None

    def _load(self) -> Any:
        if self._model is None:
            from sentence_transformers import CrossEncoder

            self._model = CrossEncoder(self._model_name)
        return self._model

    async def rerank(
        self, query: str, passages: list[ScoredPassage], *, top_n: int
    ) -> list[ScoredPassage]:
        if not passages:
            return []
        model = self._load()
        pairs = [(query, passage.content) for passage in passages]
        raw_scores = model.predict(pairs)
        scores = [float(score) for score in raw_scores]
        ranked = sorted(
            zip(scores, passages, strict=True),
            key=lambda item: float(item[0]),
            reverse=True,
        )[:top_n]
        return [
            ScoredPassage(
                chunk_id=passage.chunk_id,
                content=passage.content,
                score=float(score),
                channel="reranked",
                document_id=passage.document_id,
                meta={**passage.meta, "rerank_score": float(score)},
            )
            for score, passage in ranked
        ]


def build_reranker(*, model_name: str, enabled: bool) -> Reranker | None:
    if not enabled:
        return None
    try:
        import sentence_transformers  # noqa: F401

        return CrossEncoderReranker(model_name)
    except ImportError:
        return FakeReranker()
