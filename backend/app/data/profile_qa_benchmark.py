"""Labelled profile Q/A pairs for retrieval benchmarks."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ProfileQAPair:
    question: str
    relevant_phrases: tuple[str, ...]


PROFILE_QA_BENCHMARK: tuple[ProfileQAPair, ...] = (
    ProfileQAPair(
        "Which machine learning frameworks does the user know?",
        ("pytorch", "tensorflow"),
    ),
    ProfileQAPair(
        "Where is the user based?",
        ("bangalore", "india"),
    ),
    ProfileQAPair(
        "What is the user's salary expectation?",
        ("90000", "eur"),
    ),
    ProfileQAPair(
        "Does the user have EU work authorization?",
        ("work authorization", "germany"),
    ),
    ProfileQAPair(
        "What cloud platforms has the user worked with?",
        ("aws", "gcp"),
    ),
)

SAMPLE_PROFILE_DOCUMENT = """
Professional Summary
Experienced AI engineer based in Bangalore, India with 6 years building production ML systems.

Skills
- PyTorch and TensorFlow for model training
- AWS and GCP for deployment
- Python, FastAPI, PostgreSQL

Work Authorization
Eligible to work in India. Requires visa sponsorship for Germany.

Compensation
Target compensation is 90000 EUR per year for senior roles in the EU.
""".strip()
