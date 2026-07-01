#!/usr/bin/env python3
"""extract.py — Convert PaperContent JSON into StrategySpec(s) JSON.

Supports multi-strategy papers: when a paper contains multiple independent
strategies, each is extracted separately into its own StrategySpec.

Usage (CLI):
    python scripts/extract.py <slug>/inputs/content.json     # default output
    python scripts/extract.py <slug>/inputs/content.json -o spec.json   # custom

Usage (agent):
    Run after parse.py; reads the inputs/content.json artifact.

Input:  PaperContent JSON (from parse.py)
Output: ExtractionResult JSON (array of StrategySpec objects) — by default
        written under <slug>/inputs/spec.json.
"""

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from paper2spec.extractor import extract_spec
from paper2spec.models import PaperContent
from paper2spec.paths import paper_layout_from_pdf


def _load_instruction_context(paths: list[str], instructions_dir: str | None) -> str:
    """Load optional instruction/clarification files for grounded extraction."""
    files: list[Path] = []
    for raw in paths:
        p = Path(raw)
        if p.is_file():
            files.append(p)
    if instructions_dir:
        d = Path(instructions_dir)
        if d.is_dir():
            patterns = ("*instruction*.md", "*clarification*.md", "*reference*.md")
            seen = {p.resolve() for p in files}
            for pattern in patterns:
                for p in sorted(d.glob(pattern)):
                    if p.is_file() and p.resolve() not in seen:
                        files.append(p)
                        seen.add(p.resolve())

    chunks = []
    for p in files:
        try:
            chunks.append(f"\n\n=== {p.name} ===\n" + p.read_text(encoding="utf-8"))
        except OSError as exc:
            logging.warning("Could not read instruction file %s: %s", p, exc)
    return "".join(chunks)


def _infer_slug_from_content_path(content_path: str) -> str | None:
    """Best-effort slug inference: walk up from inputs/content.{md,json}.

    If the content JSON lives at ``<root>/<slug>/inputs/content.json``, this
    returns ``<slug>``. Otherwise returns ``None``.
    """
    p = Path(content_path).resolve()
    if p.parent.name == "inputs" and p.parent.parent.name:
        return p.parent.parent.name
    return None


def main():
    parser = argparse.ArgumentParser(
        description="Extract StrategySpec(s) from PaperContent JSON."
    )
    parser.add_argument("content_path", help="Path to content.md (from parse.py) or legacy content.json")
    parser.add_argument(
        "-o", "--output",
        help="Output JSON path (default: <slug>/inputs/spec.json)",
    )
    parser.add_argument(
        "--model",
        help="Override LLM model",
    )
    parser.add_argument(
        "--instruction",
        action="append",
        default=[],
        help="Extra instruction/clarification Markdown file to ground extraction. Can be repeated.",
    )
    parser.add_argument(
        "--instructions-dir",
        help="Directory containing *instruction*.md, *clarification*.md, or *reference*.md files.",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    if not os.path.isfile(args.content_path):
        print(f"Error: file not found: {args.content_path}", file=sys.stderr)
        sys.exit(1)

    # Load content — accept both .md (new) and .json (backward compat)
    if args.content_path.endswith(".json"):
        with open(args.content_path, "r", encoding="utf-8") as f:
            pc = PaperContent.from_dict(json.load(f))
    else:
        # .md file — extractor accepts str | PaperContent
        content_md = Path(args.content_path).read_text(encoding="utf-8")
        pc = content_md  # pass string directly

    instruction_context = _load_instruction_context(args.instruction, args.instructions_dir)
    if instruction_context:
        logging.info("Loaded %d chars of instruction/clarification context", len(instruction_context))

    # Extract (returns ExtractionResult with list of specs)
    result = extract_spec(pc, model=args.model, instruction_context=instruction_context)

    # Output path
    if args.output:
        out_path = args.output
    else:
        slug = _infer_slug_from_content_path(args.content_path)
        if slug:
            from paper2spec.paths import paper_layout
            layout = paper_layout(slug)
            layout.ensure()
            out_path = str(layout.input_path("spec.json"))
        else:
            # Fallback: legacy <stem>_spec.json next to the input
            stem = os.path.splitext(os.path.basename(args.content_path))[0]
            stem = stem.replace("_content", "")
            out_path = f"{stem}_spec.json"
            print(
                f"⚠️  Could not infer per-paper layout from {args.content_path}; "
                f"writing to legacy location {out_path}",
                file=sys.stderr,
            )

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(result.to_json())

    # Also write human-readable markdown
    from paper2spec.render import spec_to_markdown
    spec_md_path = os.path.splitext(out_path)[0] + ".md"
    with open(spec_md_path, "w", encoding="utf-8") as f:
        f.write(spec_to_markdown(result))

    print(f"\n✅ Wrote {out_path} ({os.path.getsize(out_path)} bytes)")
    print(f"   Wrote {spec_md_path}")
    print(f"   Paper: {result.paper_title}")
    print(f"   Strategies detected: {result.num_detected}")
    for i, spec in enumerate(result.strategies):
        print(f"\n   [{i+1}] {spec.strategy_name} ({spec.strategy_type})")
        print(f"       Indicators: {len(spec.indicators)}")
        print(f"       Logic Steps: {len(spec.logic_pipeline)}")
        print(f"       Execution Plans: {len(spec.execution_plan)}")


if __name__ == "__main__":
    main()
