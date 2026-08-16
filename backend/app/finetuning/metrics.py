"""Extraction evaluation metrics."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from app.schemas.extraction import OpportunityExtraction

EXTRACTION_GATES: dict[str, float] = {
    "classification_accuracy": 0.92,
    "deadline_accuracy": 0.90,
    "requirement_f1": 0.80,
}


@dataclass(frozen=True, slots=True)
class ExtractionMetrics:
    classification_accuracy: float
    deadline_accuracy: float
    requirement_f1: float

    def as_dict(self) -> dict[str, float]:
        return {
            "classification_accuracy": self.classification_accuracy,
            "deadline_accuracy": self.deadline_accuracy,
            "requirement_f1": self.requirement_f1,
        }

    @property
    def macro_average(self) -> float:
        values = self.as_dict()
        return sum(values.values()) / len(values)

    def gate_failures(self) -> tuple[str, ...]:
        failures: list[str] = []
        for metric, minimum in EXTRACTION_GATES.items():
            value = self.as_dict()[metric]
            if value < minimum:
                failures.append(f"{metric}={value:.3f} below minimum {minimum:.3f}")
        return tuple(failures)


def evaluate_extractions(
    *,
    predictions: list[OpportunityExtraction],
    gold: list[OpportunityExtraction],
) -> ExtractionMetrics:
    if len(predictions) != len(gold) or not gold:
        return ExtractionMetrics(0.0, 0.0, 0.0)
    classification_hits = 0
    deadline_hits = 0
    requirement_scores: list[float] = []
    for predicted, expected in zip(predictions, gold, strict=True):
        if predicted.category == expected.category:
            classification_hits += 1
        if _deadline_match(predicted.deadline, expected.deadline):
            deadline_hits += 1
        requirement_scores.append(
            _set_f1(
                _normalized_terms(predicted.required_skills + predicted.requirements),
                _normalized_terms(expected.required_skills + expected.requirements),
            )
        )
    total = len(gold)
    return ExtractionMetrics(
        classification_accuracy=classification_hits / total,
        deadline_accuracy=deadline_hits / total,
        requirement_f1=sum(requirement_scores) / total,
    )


def _deadline_match(predicted: date | None, expected: date | None) -> bool:
    if expected is None:
        return predicted is None
    return predicted == expected


def _normalized_terms(values: list[str]) -> set[str]:
    return {value.strip().casefold() for value in values if value.strip()}


def _set_f1(predicted: set[str], expected: set[str]) -> float:
    if not expected and not predicted:
        return 1.0
    if not expected or not predicted:
        return 0.0
    overlap = len(predicted & expected)
    if overlap == 0:
        return 0.0
    precision = overlap / len(predicted)
    recall = overlap / len(expected)
    return 2 * precision * recall / (precision + recall)
