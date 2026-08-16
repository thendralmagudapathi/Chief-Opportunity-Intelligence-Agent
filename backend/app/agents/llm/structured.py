"""Structured LLM output: validate, repair, retry, fallback."""

from __future__ import annotations

import json
import re
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from app.agents.llm.protocols import LLMProvider, TaskClass
from app.core.logging import get_logger

logger = get_logger(__name__)

T = TypeVar("T", bound=BaseModel)
_JSON_BLOCK = re.compile(r"\{[\s\S]*\}")


async def structured_complete(
    llm: LLMProvider,
    schema: type[T],
    prompt: str,
    *,
    task_class: TaskClass = "standard",
    system: str | None = None,
    max_attempts: int = 3,
) -> T:
    current_prompt = prompt
    last_error: str | None = None
    last_raw: str | None = None

    for attempt in range(1, max_attempts + 1):
        response = await llm.complete(current_prompt, task_class=task_class, system=system)
        last_raw = response.content
        try:
            data = _extract_json(response.content)
            return schema.model_validate(data)
        except (ValidationError, json.JSONDecodeError, ValueError) as exc:
            last_error = str(exc)
            logger.info(
                "structured_output_repair",
                schema=schema.__name__,
                attempt=attempt,
                error=last_error,
            )
            current_prompt = _repair_prompt(
                original=prompt,
                schema=schema,
                raw=last_raw or "",
                error=last_error,
            )

    if last_raw is not None:
        try:
            return schema.model_validate(_extract_json(last_raw))
        except (ValidationError, json.JSONDecodeError, ValueError):
            pass

    raise ValueError(last_error or "Structured output validation failed")


def _extract_json(raw: str) -> object:
    raw = raw.strip()
    if raw.startswith("{") or raw.startswith("["):
        return json.loads(raw)
    match = _JSON_BLOCK.search(raw)
    if match is None:
        raise ValueError("No JSON object found in model output")
    return json.loads(match.group(0))


def _repair_prompt(*, original: str, schema: type[BaseModel], raw: str, error: str) -> str:
    return (
        f"{original}\n\n"
        "Your previous answer failed validation. Return ONLY valid JSON matching "
        f"the {schema.__name__} schema.\n"
        f"Validation error: {error}\n"
        f"Previous output:\n{raw}\n"
    )
