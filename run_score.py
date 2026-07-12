#!/usr/bin/env python3
"""Score the generated dataset for fine-tuning quality.

Usage:
    uv run python run_score.py
    uv run python run_score.py --verbose
    uv run python run_score.py --pipeline-stats '{"skip_count":20,"duplicate_dropped":1060,"sentence_dropped":2892,"canned_stripped":2917,"canned_dropped":34,"broken_dropped":155,"total_raw":1666}'
"""

import argparse
import json
import logging
import sys

from src.score_dataset import score_dataset, format_report


def main():
    parser = argparse.ArgumentParser(description="Score prepared dataset quality")
    parser.add_argument("--train", default="data/train.jsonl", help="Path to train.jsonl")
    parser.add_argument("--valid", default="data/valid.jsonl", help="Path to valid.jsonl")
    parser.add_argument("--config", default="config/config.yaml", help="Path to config.yaml")
    parser.add_argument("--pipeline-stats", default=None,
                        help="JSON file or inline JSON with pipeline stats from run_prepare.py")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s | %(message)s",
    )

    # Load pipeline stats: try --pipeline-stats, then data/score_stats.json, then data/export_cursor.json
    pipeline_stats = None
    ps_paths = [
        args.pipeline_stats,
        "data/score_stats.json",
        "data/export_cursor.json",
    ]
    for ps_path in ps_paths:
        if ps_path is None:
            continue
        # Try as file path first
        try:
            with open(ps_path) as f:
                data = json.load(f)
            # Must have at least one valid field
            if isinstance(data, dict) and ("train_count" in data or "skip_count" in data or "total_raw" in data):
                pipeline_stats = data
                logging.info("Loaded pipeline stats from %s", ps_path)
                break
        except (FileNotFoundError, json.JSONDecodeError):
            pass
        # Try as inline JSON string (only for the explicitly provided arg)
        if ps_path is args.pipeline_stats and ps_path:
            try:
                pipeline_stats = json.loads(ps_path)
                logging.info("Loaded inline pipeline stats")
                break
            except (json.JSONDecodeError, TypeError):
                pass

    result = score_dataset(
        train_path=args.train,
        valid_path=args.valid,
        config_path=args.config,
        pipeline_stats=pipeline_stats,
    )

    print()
    print(format_report(result, verbose=args.verbose))

    return 0 if result["total"] >= 70 else 1


if __name__ == "__main__":
    sys.exit(main())