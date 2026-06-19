#!/usr/bin/env python3
"""discover_clickhouse.py — Scan ClickHouse schema and build a data catalog.

Usage (CLI):
    python scripts/discover_clickhouse.py                  # default output path
    python scripts/discover_clickhouse.py -o custom.yaml   # custom output path
    python scripts/discover_clickhouse.py --refresh         # force re-discovery

Usage (agent):
    The agent runs this script once to learn the database schema,
    then reads ``paper2spec/resources/clickhouse_catalog.json`` for
    all subsequent sessions.

Output: YAML catalog file listing every table with column names,
        types, row counts, and date ranges.
"""

import argparse
import logging
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from paper2spec.clickhouse import CATALOG_PATH, discover_schema, load_catalog


def main():
    parser = argparse.ArgumentParser(
        description="Discover ClickHouse schema and write a data catalog."
    )
    parser.add_argument(
        "-o", "--output",
        help=f"Output YAML path (default: {CATALOG_PATH})",
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Force re-discovery even if a catalog already exists",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    out_path = args.output or str(CATALOG_PATH)

    if not args.refresh and not args.output:
        existing = load_catalog(out_path)
        if existing is not None:
            print(f"✅ Catalog already exists at {out_path}")
            print(f"   Generated: {existing.get('generated_at', 'unknown')}")
            print(f"   Tables: {len(existing.get('tables', {}))}")
            print(f"   Use --refresh to force re-discovery")
            return

    print("🔍 Discovering ClickHouse schema...")
    catalog = discover_schema(output_path=out_path)

    total_tables = sum(len(t) for t in catalog.get("databases", {}).values())
    print(f"\n✅ Catalog written to {out_path}")
    print(f"   Host: {catalog['host']}")
    print(f"   Databases: {len(catalog.get('databases', {}))}")
    print(f"   Tables: {total_tables}")
    for db_name, tables in catalog.get("databases", {}).items():
        print(f"\n   [{db_name}]")
        for name, info in tables.items():
            dr = info.get("date_range")
            range_str = f"  {dr[0]} → {dr[1]}" if dr else ""
            print(f"     {name}: {info['row_count']:,} rows{range_str}")


if __name__ == "__main__":
    main()
