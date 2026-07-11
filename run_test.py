#!/usr/bin/env python3
"""Entry point: Interactive testing of the fine-tuned customer support model.

Usage:
    python run_test.py [--config config/config.yaml]
"""

import argparse

from src.tester import run_interactive


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Test the fine-tuned customer support model interactively."
    )
    parser.add_argument(
        "--config",
        default=None,
        help="Path to config YAML (default: config/config.yaml)",
    )
    args = parser.parse_args()

    run_interactive(config_path=args.config)


if __name__ == "__main__":
    main()
