"""Build versioned datasets under ml/datasets/."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2] / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.data.extraction_gold import DATASET_VERSION  # noqa: E402
from app.finetuning.dataset import write_extraction_gold_jsonl, write_sft_jsonl  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Build fine-tuning datasets")
    parser.add_argument(
        "--output-dir",
        default=str(Path(__file__).resolve().parent),
    )
    args = parser.parse_args()
    output_dir = Path(args.output_dir)
    gold_path = output_dir / f"extraction_gold_{DATASET_VERSION}.jsonl"
    sft_path = output_dir / f"extraction_sft_{DATASET_VERSION}.jsonl"
    export = write_extraction_gold_jsonl(gold_path)
    write_sft_jsonl(sft_path)
    print(f"gold={export.example_count} path={export.path}")
    print(f"sft path={sft_path}")


if __name__ == "__main__":
    main()
