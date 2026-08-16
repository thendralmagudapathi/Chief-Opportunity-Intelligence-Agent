"""LoRA / QLoRA SFT training for extraction."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2] / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def main() -> None:
    parser = argparse.ArgumentParser(description="Run extraction SFT with LoRA/QLoRA")
    parser.add_argument(
        "--dataset",
        default=str(Path(__file__).resolve().parents[1] / "datasets" / "extraction_sft_v1.jsonl"),
    )
    parser.add_argument("--base-model", default="Qwen/Qwen2.5-7B-Instruct")
    parser.add_argument("--output-dir", default="./artifacts/extraction-lora")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--qlora", action="store_true")
    args = parser.parse_args()

    dataset_path = Path(args.dataset)
    if not dataset_path.exists():
        raise SystemExit(f"dataset not found: {dataset_path}")

    rows = [json.loads(line) for line in dataset_path.read_text(encoding="utf-8").splitlines() if line]
    manifest = {
        "base_model": args.base_model,
        "dataset": str(dataset_path),
        "rows": len(rows),
        "qlora": args.qlora,
        "dry_run": args.dry_run,
    }
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / "train_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    if args.dry_run:
        print(json.dumps(manifest, indent=2))
        return

    try:
        import torch
        from datasets import load_dataset
        from peft import LoraConfig, TaskType, get_peft_model
        from transformers import AutoModelForCausalLM, AutoTokenizer, TrainingArguments
        from transformers import Trainer as HfTrainer
    except ImportError as exc:
        raise SystemExit(
            "Install finetuning extras: pip install 'oia-backend[finetuning]'"
        ) from exc

    dataset = load_dataset("json", data_files=str(dataset_path), split="train")

    def format_row(row: dict[str, str]) -> dict[str, str]:
        text = (
            f"### Instruction:\n{row['instruction']}\n\n"
            f"### Input:\n{row['input']}\n\n"
            f"### Response:\n{row['output']}"
        )
        return {"text": text}

    formatted = dataset.map(format_row)
    tokenizer = AutoTokenizer.from_pretrained(args.base_model, trust_remote_code=True)
    model = AutoModelForCausalLM.from_pretrained(
        args.base_model,
        torch_dtype=torch.float16 if args.qlora else torch.float32,
        device_map="auto" if torch.cuda.is_available() else None,
        trust_remote_code=True,
    )
    lora = LoraConfig(
        task_type=TaskType.CAUSAL_LM,
        r=16,
        lora_alpha=32,
        lora_dropout=0.05,
        target_modules=["q_proj", "v_proj"],
    )
    model = get_peft_model(model, lora)

    def tokenize(batch: dict[str, list[str]]) -> dict[str, list[list[int]]]:
        return tokenizer(batch["text"], truncation=True, max_length=2048)

    tokenized = formatted.map(tokenize, batched=True, remove_columns=formatted.column_names)
    training_args = TrainingArguments(
        output_dir=str(output_dir),
        num_train_epochs=1,
        per_device_train_batch_size=1,
        logging_steps=10,
        save_strategy="epoch",
        report_to=[],
    )
    trainer = HfTrainer(model=model, args=training_args, train_dataset=tokenized)
    trainer.train()
    model.save_pretrained(str(output_dir / "adapter"))
    tokenizer.save_pretrained(str(output_dir / "adapter"))
    print(f"saved adapter to {output_dir / 'adapter'}")


if __name__ == "__main__":
    main()
