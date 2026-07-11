#!/usr/bin/env python3
"""Entry point: Build conversation objects from raw Zendesk tickets and generate
train.jsonl / valid.jsonl in Unsloth chat format.

Usage:
    python run_prepare.py [--config config/config.yaml] [--analyze]
"""

import argparse
import json
import sys

from src.common.config import get_dataset_config, load_config
from src.dataset import (
    build_conversation,
    generate_dataset,
    _analyze_sentences,
    _split_sentences,
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
    dedupe_sent = cfg.get("dedupe_sentences", True)
    filter_sentences = cfg.get("filter_sentences", [])
    clean_fillers = cfg.get("clean_fillers", True)
    drop_filler_only = cfg.get("drop_filler_only", True)

    if args.analyze:
        return _run_analyze(input_dir, agent_names, clean_attachments,
                            clean_urls, redact_pii, pii_safe, clean_fillers,
                            drop_filler_only, min_msg_len)

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
        dedupe_sentences=dedupe_sent,
        filter_sentences=filter_sentences,
        clean_fillers=clean_fillers,
        drop_filler_only=drop_filler_only,
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


def _run_analyze(
    input_dir: str,
    agent_names: list[str],
    clean_attachments: bool,
    clean_urls: bool,
    redact_pii: bool,
    pii_safe: list[str],
    clean_fillers: bool,
    drop_filler_only: bool,
    min_msg_len: int,
) -> int:
    """Analyze sentence frequencies and output candidates for filter_sentences."""
    import os
    from pathlib import Path

    raw_path = Path(input_dir)
    if not raw_path.exists():
        print(f"Error: input directory '{input_dir}' does not exist.")
        return 1

    agent_set = set(agent_names) if agent_names else set()
    all_convs = []

    for fn in sorted(os.listdir(raw_path)):
        if not fn.endswith(".json"):
            continue
        with open(raw_path / fn) as f:
            ticket = json.load(f)
        conv = build_conversation(
            ticket,
            agent_names=agent_set,
            clean_attachments=clean_attachments,
            clean_urls=clean_urls,
            redact_pii=redact_pii,
            clean_fillers=clean_fillers,
            drop_filler_only=drop_filler_only,
            pii_safe_patterns=pii_safe,
            min_length=min_msg_len,
        )
        if conv and conv.get("conversation"):
            all_convs.append(conv)

    candidates = _analyze_sentences(all_convs, top_n=60)
    print(f"\nAnalyzed {len(all_convs)} conversations.")
    print(f"Top {len(candidates)} candidate sentences for filtering:\n")

    for i, (sent, count) in enumerate(candidates, 1):
        role = "n/a"
        # Find the role of this sentence
        for conv in all_convs:
            for turn in conv["conversation"]:
                if sent in turn["content"]:
                    role = turn["role"]
                    break
            if role != "n/a":
                break

        preview = sent[:80] + "..." if len(sent) > 80 else sent
        print(f"  {i:>3}. [{role:>8}] ({count:>4}x) \"{preview}\"")

    print(f"\nAdd chosen sentences to 'filter_sentences' in config/dataset section.")
    print("Example YAML:")
    print("  filter_sentences:")
    for sent, _ in candidates[:5]:
        # Truncate to 120 chars for display
        display = sent[:120]
        print(f'    - "{display}"')
    print("  # ... add more from the list above")

    return 0


if __name__ == "__main__":
    sys.exit(main())