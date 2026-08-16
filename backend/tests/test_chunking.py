"""Chunking behaviour."""

from __future__ import annotations

from app.retrieval.chunking import chunk_text, estimate_tokens


def test_estimate_tokens_is_conservative() -> None:
    assert estimate_tokens("one two three four") >= 4


def test_chunk_text_respects_overlap() -> None:
    text = "\n\n".join(f"Paragraph {index} " + ("word " * 80) for index in range(6))
    chunks = chunk_text(text, max_tokens=120, overlap_tokens=20)
    assert len(chunks) > 1
    assert all(chunk.content for chunk in chunks)
