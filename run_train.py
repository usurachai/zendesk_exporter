#!/usr/bin/env python3
"""Entry point: Fine-tune Qwen2.5-1.5B-Instruct with LoRA using Unsloth.

Usage:
    python run_train.py [--config config/config.yaml]
"""

import argparse
import sys

from src.trainer import run_training


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fine-tune Qwen2.5-1.5B-Instruct with LoRA."
    )
    parser.add_argument(
        "--config",
        default=None,
        help="Path to config YAML (default: config/config.yaml)",
    )
    parser.add_argument(
        "--train",
        default=None,
        help="Override path to train.jsonl",
    )
    parser.add_argument(
        "--valid",
        default=None,
        help="Override path to valid.jsonl",
    )
    parser.add_argument(
        "--base_model",
        default=None,
        help="Override base model (e.g., unsloth/Qwen2.5-7B-Instruct)",
    )
    args = parser.parse_args()

    print("Starting LoRA fine-tuning...")
    print("This requires a GPU with CUDA support and significant RAM.")
    print()

    result = run_training(
        config_path=args.config,
        train_path=args.train,
        valid_path=args.valid,
        base_model=args.base_model,
    )

    print(f"\nTraining {result['status']}!")
    if "adapter_path" in result:
        print(f"Adapter saved to: {result['adapter_path']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
