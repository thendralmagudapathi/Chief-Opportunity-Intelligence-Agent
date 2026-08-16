"""Four-way extraction baseline comparison."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.agents.llm.protocols import LLMProvider
from app.data.extraction_gold import ExtractionGoldExample, load_extraction_gold
from app.evaluation.gates import NOISE_BAND_SIGMA
from app.finetuning.baselines import BaselineMode, KeywordBaselineExtractor, LLMBaselineExtractor
from app.finetuning.metrics import ExtractionMetrics, evaluate_extractions
from app.schemas.extraction import OpportunityExtraction


class ComparisonVerdict(StrEnum):
    PROMOTED = "promoted"
    NEGATIVE = "negative"
    INCONCLUSIVE = "inconclusive"


@dataclass(frozen=True, slots=True)
class ModeScore:
    mode: BaselineMode
    metrics: ExtractionMetrics

    @property
    def macro_average(self) -> float:
        return self.metrics.macro_average


@dataclass(frozen=True, slots=True)
class ComparisonResult:
    scores: tuple[ModeScore, ...]
    winner: BaselineMode
    prompted: ModeScore
    candidate: ModeScore
    lift: float
    noise_band: float
    verdict: ComparisonVerdict
    notes: str


class ExtractionComparisonHarness:
    """Compare keyword, prompted, RAG, and RAG+FT extraction modes."""

    FEW_SHOT_K = 2

    def __init__(self, llm: LLMProvider) -> None:
        self.llm = llm
        self.keyword = KeywordBaselineExtractor()
        self.llm_extractor = LLMBaselineExtractor(llm)

    async def run(
        self,
        *,
        examples: tuple[ExtractionGoldExample, ...] | None = None,
        noise_band: float = 0.02,
    ) -> ComparisonResult:
        dataset = examples or load_extraction_gold()
        scores: list[ModeScore] = []
        for mode in BaselineMode:
            predictions = await self._predict_all(dataset, mode=mode)
            gold = [row.label for row in dataset]
            metrics = evaluate_extractions(predictions=predictions, gold=gold)
            scores.append(ModeScore(mode=mode, metrics=metrics))

        prompted = next(score for score in scores if score.mode == BaselineMode.PROMPTED)
        candidate = next(score for score in scores if score.mode == BaselineMode.RAG_FT)
        lift = candidate.macro_average - prompted.macro_average
        winner = max(scores, key=lambda item: item.macro_average).mode
        verdict, notes = _decide_verdict(
            lift=lift,
            noise_band=noise_band,
            candidate=candidate,
            prompted=prompted,
        )
        return ComparisonResult(
            scores=tuple(scores),
            winner=winner,
            prompted=prompted,
            candidate=candidate,
            lift=lift,
            noise_band=noise_band,
            verdict=verdict,
            notes=notes,
        )

    async def _predict_all(
        self,
        dataset: tuple[ExtractionGoldExample, ...],
        *,
        mode: BaselineMode,
    ) -> list[OpportunityExtraction]:
        predictions: list[OpportunityExtraction] = []
        for index, example in enumerate(dataset):
            if mode == BaselineMode.KEYWORD:
                predicted = await self.keyword.extract(example.posting_text)
            else:
                few_shot = _few_shot_examples(dataset, index, k=self.FEW_SHOT_K)
                predicted = await self.llm_extractor.extract(
                    example.posting_text,
                    mode=mode,
                    few_shot=few_shot,
                )
            predictions.append(predicted)
        return predictions


def _few_shot_examples(
    dataset: tuple[ExtractionGoldExample, ...],
    holdout_index: int,
    *,
    k: int,
) -> tuple[ExtractionGoldExample, ...]:
    selected: list[ExtractionGoldExample] = []
    for offset, example in enumerate(dataset):
        if offset == holdout_index:
            continue
        selected.append(example)
        if len(selected) >= k:
            break
    return tuple(selected)


def _decide_verdict(
    *,
    lift: float,
    noise_band: float,
    candidate: ModeScore,
    prompted: ModeScore,
) -> tuple[ComparisonVerdict, str]:
    candidate_failures = candidate.metrics.gate_failures()
    if candidate_failures:
        return (
            ComparisonVerdict.NEGATIVE,
            f"RAG+FT failed gates: {', '.join(candidate_failures)}",
        )
    if lift <= noise_band:
        return (
            ComparisonVerdict.NEGATIVE,
            f"lift {lift:.3f} did not exceed noise band {noise_band:.3f} "
            f"(prompted={prompted.macro_average:.3f}, rag_ft={candidate.macro_average:.3f})",
        )
    return (
        ComparisonVerdict.PROMOTED,
        f"RAG+FT beat prompted by {lift:.3f} (> {noise_band:.3f} noise band)",
    )


def default_noise_band() -> float:
    return NOISE_BAND_SIGMA * 0.01
