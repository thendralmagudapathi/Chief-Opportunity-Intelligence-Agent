"""Fast CI evaluation subset (~50 cases, no external network)."""

from __future__ import annotations

from dataclasses import dataclass

from app.agents.state import InvestigationState
from app.data.profile_qa_benchmark import PROFILE_QA_BENCHMARK
from app.tools.benchmark import argument_cases as tool_argument_cases
from app.tools.benchmark import selection_cases as tool_selection_benchmark


@dataclass(frozen=True, slots=True)
class RoutingCase:
    name: str
    state: InvestigationState
    expected: str


@dataclass(frozen=True, slots=True)
class FaithfulnessCase:
    name: str
    context: str
    answer: str
    must_include: tuple[str, ...]
    must_not_include: tuple[str, ...] = ()


ROUTING_CASES: tuple[RoutingCase, ...] = (
    RoutingCase("triage_empty", {"candidates": []}, "report"),
    RoutingCase("triage_candidates", {"candidates": [{"id": "1"}]}, "evaluate"),
    RoutingCase(
        "verify_replan",
        {
            "unresolved_high_impact_claims": 2,
            "iterations": 0,
            "budget": {"max_iterations": 3, "remaining_usd": 1.0},
        },
        "replan",
    ),
    RoutingCase(
        "verify_score",
        {
            "unresolved_high_impact_claims": 0,
            "iterations": 0,
            "budget": {"max_iterations": 3, "remaining_usd": 1.0},
        },
        "score",
    ),
    RoutingCase("replan_discover", {"plan": {"needs_new_sources": True}}, "discover"),
    RoutingCase("replan_evaluate", {"plan": {"needs_new_sources": False}}, "evaluate"),
)

_QUESTION_VARIANTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Which ML frameworks?", ("pytorch", "tensorflow")),
    ("What is the user's location?", ("bangalore", "india")),
    ("Salary expectations?", ("90000", "eur")),
    ("Work authorization in Germany?", ("work authorization", "germany")),
    ("Cloud experience?", ("aws", "gcp")),
)

_EXTRA_RETRIEVAL_CASES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Does the profile mention PyTorch?", ("pytorch",)),
    ("Any TensorFlow experience?", ("tensorflow",)),
    ("Where in India is the user?", ("bangalore", "india")),
    ("Target EUR compensation?", ("90000", "eur")),
    ("Visa requirements for Germany?", ("visa", "germany")),
    ("AWS or GCP experience?", ("aws", "gcp")),
    ("FastAPI backend skills?", ("fastapi",)),
    ("Python programming background?", ("python",)),
    ("PostgreSQL database experience?", ("postgresql",)),
    ("Production ML systems?", ("production",)),
    ("AI engineer summary?", ("ai engineer",)),
    ("Senior EU role pay?", ("90000",)),
)


def retrieval_cases() -> list[tuple[str, str, tuple[str, ...]]]:
    cases: list[tuple[str, str, tuple[str, ...]]] = []
    for pair in PROFILE_QA_BENCHMARK:
        cases.append((pair.question, pair.question, pair.relevant_phrases))
    for question, phrases in _QUESTION_VARIANTS:
        cases.append((question, question, phrases))
    for question, phrases in _EXTRA_RETRIEVAL_CASES:
        cases.append((question, question, phrases))
    return cases[:25]


def tool_selection_cases() -> list[tuple[str, str]]:
    return [(case.prompt, case.expected_tool) for case in tool_selection_benchmark()]


def tool_argument_cases_list() -> list[tuple[str, dict[str, object], bool]]:
    return [(case.tool_name, case.arguments, case.valid) for case in tool_argument_cases()]


def routing_case_evaluators() -> list[RoutingCase]:
    return list(ROUTING_CASES)


def faithfulness_cases() -> list[FaithfulnessCase]:
    return [
        FaithfulnessCase(
            name=f"faithfulness_{index}",
            context="The user knows PyTorch and TensorFlow.",
            answer="The user knows PyTorch and TensorFlow.",
            must_include=("pytorch", "tensorflow"),
        )
        for index in range(5)
    ] + [
        FaithfulnessCase(
            name="faithfulness_no_hallucination",
            context="Target compensation is 90000 EUR.",
            answer="Target compensation is 90000 EUR.",
            must_include=("90000",),
            must_not_include=("usd", "million"),
        )
    ]


def total_case_count() -> int:
    return (
        len(retrieval_cases())
        + len(tool_selection_cases())
        + len(tool_argument_cases_list())
        + len(ROUTING_CASES)
        + len(faithfulness_cases())
    )
