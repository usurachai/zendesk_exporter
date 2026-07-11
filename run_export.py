#!/usr/bin/env python3
"""Entry point: Export Zendesk Facebook Messenger tickets to raw JSON.

Usage:
    python run_export.py [--config config/config.yaml]
    python run_export.py --start-date 2024-01-01 --end-date 2024-12-31
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
    parser.add_argument(
        "--start-date",
        default=None,
        help="ISO date to start export from (e.g. 2024-01-01)",
    )
    parser.add_argument(
        "--end-date",
        default=None,
        help="ISO date to stop export at (e.g. 2024-12-31)",
    )
    args = parser.parse_args()

    print("Starting Zendesk export...")
    if args.start_date:
        print(f"  From: {args.start_date}")
    if args.end_date:
        print(f"  To:   {args.end_date}")
    print()

    result = run_export(
        config_path=args.config,
        start_date=args.start_date,
        end_date=args.end_date,
    )

    if "error" in result:
        print(f"\nExport completed with errors: {result['error']}")
        print(f"Tickets exported: {result.get('tickets_exported', 0)}")
        return 1

    print(f"\nExport completed successfully!")
    print(f"  Tickets found:     {result.get('tickets_found', 0)}")
    print(f"  Tickets exported:  {result['tickets_exported']}")
    if result.get("tickets_failed"):
        print(f"  Tickets failed:    {result['tickets_failed']}")
    print(f"  Time elapsed:      {result['elapsed_seconds']}s")
    print(f"  Output directory:  {result['output_dir']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
