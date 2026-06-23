#!/usr/bin/env python3
"""render_run_config.py — extract paper-specific settings into config/run_config.yaml.

Reads a StrategySpec (or ExtractionResult wrapping strategies) and
writes a YAML config the agent's generated strategy.py can load via
:func:`utils.config.load_run_config`.

Usage:
    python scripts/render_run_config.py <spec.json> [-o <run_config.yaml>]

If `-o` is omitted, the config is written next to the spec at
`<spec_dir>/../config/run_config.yaml`. For a typical layout::

    spec at: replications/<slug>/inputs/spec.json
    config:  replications/<slug>/config/run_config.yaml

The agent should re-run this script after any spec edit. It is
deterministic — same input spec always produces the same output config.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from paper2spec.config import load_project_env
load_project_env()

from utils.config import render_run_config, RunConfigError


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Render per-paper run_config.yaml from a StrategySpec JSON."
    )
    parser.add_argument("spec_json", help="Path to spec.json (or ExtractionResult)")
    parser.add_argument(
        "-o", "--output",
        help="Output YAML path. Default: <spec_dir>/../config/run_config.yaml",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite the output file if it already exists",
    )
    args = parser.parse_args()

    spec_path = Path(args.spec_json).expanduser().resolve()
    if not spec_path.is_file():
        raise SystemExit(f"ERROR: spec file not found: {spec_path}")

    with spec_path.open("r", encoding="utf-8") as f:
        spec = json.load(f)

    if args.output:
        out_path = Path(args.output).expanduser().resolve()
    else:
        # Default: <spec_dir>/inputs/spec.json → <spec_dir>/config/run_config.yaml
        out_path = spec_path.parent.parent / "config" / "run_config.yaml"

    if out_path.exists() and not args.force:
        raise SystemExit(
            f"ERROR: {out_path} already exists. Use --force to overwrite."
        )

    yaml_text = render_run_config(spec)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(yaml_text, encoding="utf-8")

    print(f"✅ Wrote {out_path} ({len(yaml_text)} bytes)")
    print()
    print("Preview:")
    for line in yaml_text.splitlines()[:25]:
        print(f"  {line}")


if __name__ == "__main__":
    main()