#!/usr/bin/env python3
"""Entry point: Build conversation objects from raw Zendesk tickets and generate
train.jsonl / valid.jsonl in Unsloth chat format.

Usage:
    python run_prepare.py [--config config/config.yaml] [--analyze] [--verbose]
"""

import argparse
import logging
import sys

from src.common.config import get_dataset_config, load_config
from src.dataset import (
    generate_dataset,
    _build_conversations,
    _analyze_sentences,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build training dataset from raw Zendesk tickets."
    )
    parser.add_argument(
        "--config",
        default=None,
        help="Path to config YAML (default: config/config.yaml)",
    )
    parser.add_argument(
        "--analyze",
        action="store_true",
        help="Analyze sentence frequencies and output filter candidates",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable DEBUG-level logging",
    )
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger("src.dataset").setLevel(logging.DEBUG)

    # Load config once, pass to all functions
    if args.config:
        cfg = load_config(args.config).get("dataset", {})
    else:
        cfg = get_dataset_config()

    if args.analyze:
        return _run_analyze(cfg)

    print(f"Building dataset from {cfg.get('input_dir', 'data/raw')}...")
    result = generate_dataset(
        raw_dir=cfg.get("input_dir", "data/raw"),
        output_dir=cfg.get("output_dir", "data"),
        train_ratio=cfg.get("train_ratio", 0.9),
        shuffle_seed=cfg.get("shuffle_seed", 42),
        system_prompt=cfg.get("system_prompt", "").strip(),
        agent_names=cfg.get("agent_names", []),
        clean_attachments=cfg.get("clean_attachments", True),
        clean_urls=cfg.get("clean_urls", True),
        dedupe_canned=cfg.get("dedupe_canned", True),
        redact_pii=cfg.get("redact_pii", True),
        clean_fillers=cfg.get("clean_fillers", True),
        drop_filler_only=cfg.get("drop_filler_only", True),
        pii_safe_patterns=cfg.get("pii_safe_patterns", []),
        dedupe_exact=cfg.get("dedupe_exact", True),
        max_duplicate_count=cfg.get("max_duplicate_count", 3),
        dedupe_sentences=cfg.get("dedupe_sentences", True),
        filter_sentences=cfg.get("filter_sentences", []),
        min_message_length=cfg.get("min_message_length", 3),
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


def _run_analyze(cfg: dict) -> int:
    """Analyze sentence frequencies and output candidates for filter_sentences."""
    input_dir = cfg.get("input_dir", "data/raw")
    agent_names = set(cfg.get("agent_names", []))

    conversations = _build_conversations(
        raw_dir=input_dir,
        agent_names=agent_names,
        clean_attachments=cfg.get("clean_attachments", True),
        clean_urls=cfg.get("clean_urls", True),
        redact_pii=cfg.get("redact_pii", True),
        clean_fillers=cfg.get("clean_fillers", True),
        drop_filler_only=cfg.get("drop_filler_only", True),
        pii_safe_patterns=cfg.get("pii_safe_patterns", []),
        min_length=cfg.get("min_message_length", 3),
    )

    if not conversations:
        print(f"Error: no conversations built from '{input_dir}'.")
        return 1

    candidates = _analyze_sentences(conversations, top_n=60)
    print(f"\nAnalyzed {len(conversations)} conversations.")
    print(f"Top {len(candidates)} candidate sentences for filtering:\n")

    for i, (sent, count, role) in enumerate(candidates, 1):
        preview = sent[:80] + "..." if len(sent) > 80 else sent
        print(f"  {i:>3}. [{role:>8}] ({count:>4}x) \"{preview}\"")

    print(f"\nAdd chosen sentences to 'filter_sentences' in config/dataset section.")
    print("Example YAML:")
    print("  filter_sentences:")
    for sent, _, _ in candidates[:5]:
        display = sent[:120]
        print(f'    - "{display}"')
    print("  # ... add more from the list above")

    return 0


if __name__ == "__main__":
    sys.exit(main())
