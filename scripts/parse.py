#!/usr/bin/env python3
"""parse.py — Extract structured content from a quantitative finance paper PDF.

Usage (CLI):
    python scripts/parse.py paper.pdf                    # OCR + write content.md
    python scripts/parse.py paper.pdf -o content.md      # custom output path
    python scripts/parse.py paper.pdf --force-ocr        # ignore cache, re-OCR

Output: Markdown file with HTML tables and LaTeX equations, written under
``<slug>/inputs/content.md``.

The extractor (extract.py) reads this file directly — no JSON intermediate.
"""

import argparse
import logging
import os
import sys
from pathlib import Path

# Allow running from repo root or scripts/
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from paper2spec.parser import parse_pdf
from paper2spec.paths import paper_layout_from_pdf


def main():
    parser = argparse.ArgumentParser(
        description="Parse a quantitative finance paper PDF into content.md (markdown)."
    )
    parser.add_argument("pdf", help="Path to the PDF file")
    parser.add_argument(
        "-o", "--output",
        help="Output path (default: <PAPER2SPEC_REPLICATIONS_PATH>/<pdf_stem>/inputs/content.md)",
    )
    parser.add_argument(
        "--force-ocr",
        action="store_true",
        help="Force re-OCR even if a cached full.md exists",
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

    if not os.path.isfile(args.pdf):
        print(f"Error: file not found: {args.pdf}", file=sys.stderr)
        sys.exit(1)

    # Parse (OCR via LightOnOCR-2 with automatic global cache)
    pc = parse_pdf(args.pdf, force_ocr=args.force_ocr)

    # Output path — defaults to the per-paper inputs/ directory
    if args.output:
        out_path = args.output
    else:
        layout = paper_layout_from_pdf(args.pdf)
        layout.ensure()
        out_path = str(layout.input_path("content.md"))

    out_parent = os.path.dirname(out_path)
    if out_parent:
        os.makedirs(out_parent, exist_ok=True)

    # Write content.md (raw OCR markdown)
    Path(out_path).write_text(pc.full_text, encoding="utf-8")

    print(f"✅ Wrote {out_path} ({os.path.getsize(out_path)} bytes)")
    print(f"   Title: {pc.title}")
    print(f"   Full text: {len(pc.full_text)} chars")


if __name__ == "__main__":
    main()
