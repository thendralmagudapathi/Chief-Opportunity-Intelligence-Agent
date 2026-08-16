"""Evaluation harness CLI.

Usage:
    python -m ml.evaluation.runner --suite ci --dataset-version v1
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import uuid
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2] / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


async def _run(args: argparse.Namespace) -> int:
    from app.core.config import get_settings
    from app.db.session import get_session_factory
    from app.evaluation.gates import evaluate_gates
    from app.evaluation.harness import CIHarness, run_ci_harness
    from app.evaluation.service import EvaluationService

    settings = get_settings()
    factory = get_session_factory()
    async with factory() as session:
        service = EvaluationService(session)
        row = await service.create_run(
            name=f"{args.suite}_{args.dataset_version}",
            suite=args.suite,
            dataset_name=CIHarness.DATASET_NAME,
            dataset_version=args.dataset_version,
            git_sha=settings.git_sha,
        )
        await service.mark_running(row)
        result = await run_ci_harness(
            session,
            settings,
            user_id=uuid.uuid4(),
            persist_mlflow=not args.no_mlflow,
        )
        notes = None if result.passed else "; ".join(result.failures)
        await service.mark_succeeded(row, dict(result.metrics), notes=notes)
        await session.commit()

    passed, failures = evaluate_gates(result.metrics)
    print(f"cases={result.case_count} passed={passed}")
    for key, value in sorted(result.metrics.items()):
        print(f"  {key}: {value:.3f}")
    if failures:
        print("failures:")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Run an evaluation suite")
    parser.add_argument("--suite", default="ci")
    parser.add_argument("--dataset-version", default="v1")
    parser.add_argument("--no-mlflow", action="store_true")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(_run(args)))


if __name__ == "__main__":
    main()
