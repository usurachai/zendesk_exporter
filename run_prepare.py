#!/usr/bin/env python3
"""Entry point: Build conversation objects from raw Zendesk tickets and generate
train.jsonl / valid.jsonl in Unsloth chat format.

Usage:
    python run_prepare.py [--config config/config.yaml]
"""

import argparse
import sys

from src.common.config import get_dataset_config, load_config
from src.dataset import generate_dataset


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build training dataset from raw Zendesk tickets."
    )
    parser.add_argument(
        "--config",
        default=None,
        help="Path to config YAML (default: config/config.yaml)",
    )
    args = parser.parse_args()

    if args.config:
        cfg = load_config(args.config).get("dataset", {})
    else:
        cfg = get_dataset_config()

    input_dir = cfg.get("input_dir", "data/raw")
    output_dir = cfg.get("output_dir", "data")
    train_ratio = cfg.get("train_ratio", 0.9)
    shuffle_seed = cfg.get("shuffle_seed", 42)
    system_prompt = cfg.get("system_prompt", "")
    agent_names = cfg.get("agent_names", [])
    clean_attachments = cfg.get("clean_attachments", True)
    clean_urls = cfg.get("clean_urls", True)
    dedupe_canned = cfg.get("dedupe_canned", True)
    min_msg_len = cfg.get("min_message_length", 3)
    redact_pii = cfg.get("redact_pii", True)
    pii_safe = cfg.get("pii_safe_patterns", [])
    dedupe_exact = cfg.get("dedupe_exact", True)
    max_dup = cfg.get("max_duplicate_count", 3)

    print(f"Building dataset from {input_dir}...")
    result = generate_dataset(
        raw_dir=input_dir,
        output_dir=output_dir,
        train_ratio=train_ratio,
        shuffle_seed=shuffle_seed,
        system_prompt=system_prompt.strip(),
        agent_names=agent_names,
        clean_attachments=clean_attachments,
        clean_urls=clean_urls,
        dedupe_canned=dedupe_canned,
        redact_pii=redact_pii,
        pii_safe_patterns=pii_safe,
        dedupe_exact=dedupe_exact,
        max_duplicate_count=max_dup,
        min_message_length=min_msg_len,
    )

    if "error" in result:
        print(f"Error: {result['error']}")
        return 1

    print(f"\nDataset generation complete!")
    print(f"Training samples:   {result['train_count']}")
    print(f"Validation samples: {result['valid_count']}")
    print(f"Train stats:        {result['train_stats']}")
    print(f"Train file:         {result['train_path']}")
    print(f"Valid file:         {result['valid_path']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
