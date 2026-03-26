#!/usr/bin/env python3
"""analyze.py — One-shot PDF → all outputs (content + spec + markdown).

Runs the full paper2spec pipeline:
  1. Parse PDF → PaperContent JSON + Markdown
  2. Extract PaperContent → ExtractionResult JSON + Markdown

All outputs are written to the specified output directory.

Usage:
    python scripts/analyze.py paper.pdf                     # outputs to ./paper/
    python scripts/analyze.py paper.pdf -o library/paper/    # custom output dir
    python scripts/analyze.py paper.pdf --parser-mode agent  # Mode B (FAISS)
"""

import argparse
import json
import logging
import os
import re
import shutil
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from paper2spec.extractor import extract_spec
from paper2spec.models import PaperContent
from paper2spec.parser import parse_pdf
from paper2spec.render import content_to_markdown, spec_to_markdown


def _slugify(text: str) -> str:
    """Convert a title to a filesystem-safe slug."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[-\s]+", "_", text)
    return text[:80].rstrip("_") or "paper"


def main():
    parser = argparse.ArgumentParser(
        description="Full pipeline: PDF → PaperContent + StrategySpec (JSON + Markdown)."
    )
    parser.add_argument("pdf", help="Path to the PDF file")
    parser.add_argument(
        "-o", "--output-dir",
        help="Output directory (default: ./<slugified_title>/)",
    )
    parser.add_argument(
        "--parser-mode",
        choices=["builtin", "agent"],
        default="builtin",
        help="Parser mode: 'builtin' (fast, no embeddings) or 'agent' (FAISS, better for long papers)",
    )
    parser.add_argument(
        "--extractor-mode",
        choices=["multilayer", "single"],
        default="multilayer",
        help="Extractor mode: 'multilayer' (recommended) or 'single' (legacy)",
    )
    parser.add_argument("--model", help="Override LLM model for both stages")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    if not os.path.isfile(args.pdf):
        print(f"Error: file not found: {args.pdf}", file=sys.stderr)
        sys.exit(1)

    # ── Stage 1: Parse ──
    print(f"📄 Parsing {args.pdf}...")
    pc = parse_pdf(args.pdf, mode=args.parser_mode, model=args.model)
    print(f"   Title: {pc.title}")

    # Determine output directory
    if args.output_dir:
        out_dir = args.output_dir
    else:
        out_dir = _slugify(pc.title or os.path.splitext(os.path.basename(args.pdf))[0])
    os.makedirs(out_dir, exist_ok=True)

    # Write PaperContent JSON
    content_json_path = os.path.join(out_dir, "content.json")
    with open(content_json_path, "w", encoding="utf-8") as f:
        f.write(pc.to_json())

    # Write PaperContent Markdown
    content_md_path = os.path.join(out_dir, "content.md")
    with open(content_md_path, "w", encoding="utf-8") as f:
        f.write(content_to_markdown(pc))

    print(f"   → {content_json_path} ({os.path.getsize(content_json_path):,} bytes)")
    print(f"   → {content_md_path}")

    # ── Stage 2: Extract ──
    print(f"\n🔬 Extracting strategies...")
    result = extract_spec(pc, model=args.model, mode=args.extractor_mode)

    # Write ExtractionResult JSON
    spec_json_path = os.path.join(out_dir, "spec.json")
    with open(spec_json_path, "w", encoding="utf-8") as f:
        f.write(result.to_json())

    # Write ExtractionResult Markdown
    spec_md_path = os.path.join(out_dir, "spec.md")
    with open(spec_md_path, "w", encoding="utf-8") as f:
        f.write(spec_to_markdown(result))

    print(f"   → {spec_json_path} ({os.path.getsize(spec_json_path):,} bytes)")
    print(f"   → {spec_md_path}")

    # Copy original PDF into output directory for self-contained library
    pdf_basename = os.path.basename(args.pdf)
    pdf_dest = os.path.join(out_dir, pdf_basename)
    if os.path.abspath(args.pdf) != os.path.abspath(pdf_dest):
        shutil.copy2(args.pdf, pdf_dest)
        print(f"   → {pdf_dest} (original PDF)")

    # Write metadata
    metadata = {
        "source_pdf": os.path.abspath(args.pdf),
        "pdf_file": pdf_basename,
        "paper_title": pc.title,
        "parser_mode": args.parser_mode,
        "extractor_mode": args.extractor_mode,
        "model": args.model or os.environ.get("PAPER2SPEC_MODEL", ""),
        "num_strategies": result.num_detected,
        "strategies": [s.strategy_name for s in result.strategies],
        "version": "0.3.0",
    }
    meta_path = os.path.join(out_dir, "metadata.json")
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)

    # ── Summary ──
    print(f"\n✅ Analysis complete → {out_dir}/")
    print(f"   Strategies: {result.num_detected}")
    for i, spec in enumerate(result.strategies):
        print(f"   [{i+1}] {spec.strategy_name} ({spec.strategy_type})")
        print(f"       {len(spec.indicators)} indicators, {len(spec.logic_pipeline)} logic steps")

    print(f"\n   Files:")
    print(f"     {pdf_basename:<16s} — Original PDF")
    print(f"     content.json   — PaperContent (machine-readable)")
    print(f"     content.md     — PaperContent (human-readable)")
    print(f"     spec.json      — StrategySpec (machine-readable)")
    print(f"     spec.md        — StrategySpec (human-readable)")
    print(f"     metadata.json  — Analysis metadata")


if __name__ == "__main__":
    main()
