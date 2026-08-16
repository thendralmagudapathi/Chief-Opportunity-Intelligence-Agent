"""Heuristic and optional RAGAs faithfulness scoring."""

from __future__ import annotations


def heuristic_faithfulness(*, context: str, answer: str) -> float:
    context_tokens = set(context.casefold().split())
    answer_tokens = set(answer.casefold().split())
    if not answer_tokens:
        return 0.0
    overlap = len(context_tokens & answer_tokens)
    precision = overlap / len(answer_tokens)
    recall = overlap / max(len(context_tokens), 1)
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


def faithfulness_score(*, context: str, answer: str) -> float:
    try:
        from ragas.metrics import faithfulness as ragas_faithfulness

        del ragas_faithfulness  # placeholder until wired with judge model
    except ImportError:
        pass
    return heuristic_faithfulness(context=context, answer=answer)
