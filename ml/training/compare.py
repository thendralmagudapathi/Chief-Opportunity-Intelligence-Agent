"""Four-way extraction comparison CLI."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2] / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


async def _run(args: argparse.Namespace) -> int:
    from app.agents.llm.factory import build_llm_provider
    from app.core.config import get_settings
    from app.data.extraction_gold import load_extraction_gold
    from app.finetuning.comparison import ExtractionComparisonHarness

    settings = get_settings()
    harness = ExtractionComparisonHarness(build_llm_provider(settings))
    result = await harness.run(
        examples=load_extraction_gold(limit=args.limit),
        noise_band=settings.finetuning.noise_band,
    )
    print(f"verdict={result.verdict.value} winner={result.winner.value} lift={result.lift:.3f}")
    print(f"notes: {result.notes}")
    for score in result.scores:
        metrics = score.metrics.as_dict()
        macro = score.metrics.macro_average
        print(
            f"  {score.mode.value}: macro={macro:.3f} "
            f"class={metrics['classification_accuracy']:.3f} "
            f"deadline={metrics['deadline_accuracy']:.3f} "
            f"req_f1={metrics['requirement_f1']:.3f}"
        )
    return 0 if result.verdict.value == "promoted" else 1


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare extraction baselines")
    parser.add_argument("--limit", type=int, default=20)
    args = parser.parse_args()
    raise SystemExit(asyncio.run(_run(args)))


if __name__ == "__main__":
    main()
