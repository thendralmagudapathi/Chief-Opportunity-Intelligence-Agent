"""Structure-aware, token-bounded chunking with overlap."""

from __future__ import annotations

import re

from app.retrieval.protocols import TextChunk

_WHITESPACE = re.compile(r"\s+")


def estimate_tokens(text: str) -> int:
    """Conservative token estimate without pulling in a tokenizer."""
    stripped = text.strip()
    if not stripped:
        return 0
    words = len(stripped.split())
    return max(words, len(stripped) // 4)


def _split_blocks(text: str) -> list[str]:
    normalized = text.replace("\r\n", "\n").strip()
    if not normalized:
        return []
    blocks = [block.strip() for block in re.split(r"\n{2,}", normalized) if block.strip()]
    return blocks or [normalized]


def chunk_text(
    text: str,
    *,
    max_tokens: int,
    overlap_tokens: int,
) -> list[TextChunk]:
    """Merge paragraph blocks until the token budget, then roll with overlap."""
    if max_tokens < 1:
        raise ValueError("max_tokens must be positive")
    if overlap_tokens >= max_tokens:
        raise ValueError("overlap_tokens must be smaller than max_tokens")

    blocks = _split_blocks(text)
    if not blocks:
        return []

    chunks: list[TextChunk] = []
    current: list[str] = []
    current_tokens = 0
    index = 0

    def flush() -> None:
        nonlocal index, current, current_tokens
        if not current:
            return
        content = "\n\n".join(current).strip()
        if content:
            chunks.append(
                TextChunk(index=index, content=content, token_count=estimate_tokens(content))
            )
            index += 1
        current = []
        current_tokens = 0

    for block in blocks:
        block_tokens = estimate_tokens(block)
        if block_tokens > max_tokens:
            flush()
            for piece in _split_long_block(block, max_tokens=max_tokens):
                chunks.append(
                    TextChunk(index=index, content=piece, token_count=estimate_tokens(piece))
                )
                index += 1
            continue

        if current and current_tokens + block_tokens > max_tokens:
            flush()
            if overlap_tokens and chunks:
                tail = _tail_tokens(chunks[-1].content, overlap_tokens)
                if tail:
                    current = [tail]
                    current_tokens = estimate_tokens(tail)

        current.append(block)
        current_tokens += block_tokens

    flush()
    return chunks


def _split_long_block(block: str, *, max_tokens: int) -> list[str]:
    words = _WHITESPACE.split(block.strip())
    if not words:
        return []
    pieces: list[str] = []
    start = 0
    while start < len(words):
        end = start + 1
        while end <= len(words) and estimate_tokens(" ".join(words[start:end])) <= max_tokens:
            end += 1
        if end - 1 == start:
            end = start + 1
        piece = " ".join(words[start : end - 1])
        if piece:
            pieces.append(piece)
        start = max(start + 1, end - 1)
    return pieces


def _tail_tokens(text: str, overlap_tokens: int) -> str:
    words = text.split()
    if not words:
        return ""
    collected: list[str] = []
    total = 0
    for word in reversed(words):
        collected.append(word)
        total = estimate_tokens(" ".join(reversed(collected)))
        if total >= overlap_tokens:
            break
    return " ".join(reversed(collected))
