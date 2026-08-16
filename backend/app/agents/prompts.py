"""Prompt registry."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

PROMPTS_ROOT = Path(__file__).resolve().parents[2] / "prompts"


@lru_cache
def load_prompt(agent: str, name: str, version: int = 1) -> str:
    path = PROMPTS_ROOT / agent / f"{name}.v{version}.md"
    if not path.exists():
        raise FileNotFoundError(f"Prompt not found: {path}")
    return path.read_text(encoding="utf-8")


def render_prompt(template: str, **values: object) -> str:
    rendered = template
    for key, value in values.items():
        rendered = rendered.replace(f"{{{{{key}}}}}", str(value))
    return rendered
