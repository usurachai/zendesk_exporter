#!/usr/bin/env python3
"""Entry point: Export Zendesk Facebook Messenger tickets to raw JSON.

Usage:
    python run_export.py [--config config/config.yaml]
"""

import argparse
import sys

from src.exporter import run_export


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Export Zendesk tickets to raw JSON files."
    )
    parser.add_argument(
        "--config",
        default=None,
        help="Path to config YAML (default: config/config.yaml)",
    )
    args = parser.parse_args()

    print("Starting Zendesk export...")
    result = run_export(config_path=args.config)

    if "error" in result:
        print(f"\nExport completed with errors: {result['error']}")
        print(f"Tickets exported: {result.get('tickets_exported', 0)}")
        return 1

    print(f"\nExport completed successfully!")
    print(f"Tickets exported: {result['tickets_exported']}")
    print(f"Pages processed: {result['pages']}")
    print(f"Output directory: {result['output_dir']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
