#!/usr/bin/env python3
"""analyze.py — One-shot document → all outputs (content + spec + markdown).

Runs the full paper2spec pipeline:
  1. Parse document (PDF/MD/DOCX/TXT) → PaperContent JSON + Markdown
  2. Extract PaperContent → ExtractionResult JSON + Markdown

All outputs are written into the per-paper nested layout (see SKILL.md
§Output Paths). Inputs land in ``<slug>/inputs/``; the source PDF is
copied to ``<slug>/paper/original.pdf`` so each replication is
self-contained.

Usage:
    python scripts/analyze.py paper.pdf                       # PDF input
    python scripts/analyze.py strategy.md                          # Markdown input
    python scripts/analyze.py report.docx                          # DOCX input
    python scripts/analyze.py paper.pdf -o replications/my_paper/  # custom slug
    python scripts/analyze.py paper.pdf                            # OCR + extract
"""

import argparse
import json
import logging
import os
import shutil
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from paper2spec.extractor import extract_spec
from paper2spec.models import PaperContent
from paper2spec.parser import parse_document
from paper2spec.paths import paper_layout
from paper2spec.render import content_to_markdown, spec_to_markdown
from utils.config import render_run_config, RunConfigError


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


def main():
    parser = argparse.ArgumentParser(
        description="Full pipeline: Document (PDF/MD/DOCX/TXT) → PaperContent + StrategySpec (JSON + Markdown)."
    )
    parser.add_argument("input", help="Path to document file (PDF, .md, .docx, or .txt)")
    parser.add_argument(
        "-o", "--output-dir",
        help="Output directory (default: <PAPER2SPEC_REPLICATIONS_PATH>/<slugified_title>/)",
    )
    parser.add_argument(
        "--slug",
        help="Override the auto-derived paper slug (filesystem-safe identifier)",
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
    parser.add_argument("--model", help="Override LLM model for both stages")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    if not os.path.isfile(args.input):
        print(f"Error: file not found: {args.input}", file=sys.stderr)
        sys.exit(1)

    # ── Stage 1: Parse ──
    print(f"📄 Parsing {args.input}...")
    pc = parse_document(args.input)
    print(f"   Title: {pc.title}")

    # Determine the per-paper layout
    if args.output_dir:
        # Honor an explicit override by treating it as the slug's root.
        layout_root = Path(args.output_dir).expanduser().resolve()
        from paper2spec.paths import paper_layout as _pl
        # Build a layout whose root is exactly args.output_dir (still nested).
        # If the user passed a path with /inputs/ or /paper/ already, we keep it.
        layout = _pl(slug=args.slug or layout_root.name, replications_root=layout_root.parent)
        layout.ensure()
    else:
        slug = args.slug or pc.title or os.path.splitext(os.path.basename(args.input))[0]
        layout = paper_layout(slug)
        layout.ensure()

    # Write content.md (raw OCR markdown — the single intermediate format)
    content_md_path = layout.input_path("content.md")
    with open(content_md_path, "w", encoding="utf-8") as f:
        f.write(pc.full_text)

    print(f"   → {content_md_path} ({os.path.getsize(content_md_path):,} bytes)")

    # ── Stage 2: Extract ──
    print(f"\n🔬 Extracting strategies...")
    instruction_context = _load_instruction_context(args.instruction, args.instructions_dir)
    if instruction_context:
        print(f"   Loaded instruction/clarification context ({len(instruction_context):,} chars)")
    result = extract_spec(pc, model=args.model, instruction_context=instruction_context)

    # Write ExtractionResult JSON + Markdown to inputs/
    spec_json_path = layout.input_path("spec.json")
    with open(spec_json_path, "w", encoding="utf-8") as f:
        f.write(result.to_json())

    spec_md_path = layout.input_path("spec.md")
    with open(spec_md_path, "w", encoding="utf-8") as f:
        f.write(spec_to_markdown(result))

    print(f"   → {spec_json_path} ({os.path.getsize(spec_json_path):,} bytes)")
    print(f"   → {spec_md_path}")

    # ── Generate run_config.yaml from the spec ───────────────
    # This is automatic so the agent can never forget to run
    # `scripts/render_run_config.py` between spec extraction and
    # strategy.py generation. The config is the single source of
    # truth for run parameters — strategy.py should call
    # `load_run_config(slug)` instead of hardcoding constants.
    try:
        spec_dict = json.loads(result.to_json())
        run_config_yaml = render_run_config(spec_dict)
        run_config_path = layout.config_path("run_config.yaml")
        run_config_path.parent.mkdir(parents=True, exist_ok=True)
        run_config_path.write_text(run_config_yaml, encoding="utf-8")
        print(f"   → {run_config_path} (auto-generated from spec.json)")
    except (RunConfigError, ValueError) as exc:
        # Non-fatal: the agent can still generate the config manually
        # via `scripts/render_run_config.py`. Log and continue.
        logging.warning("Could not auto-generate run_config.yaml: %s", exc)
        print(f"   ⚠  run_config.yaml not generated: {exc}")

    # Copy original source file into paper/ as original.pdf (per layout contract).
    # Skip if paper/original.pdf already exists — don't overwrite or duplicate.
    src_dest = layout.paper_pdf_path()  # default: original.pdf
    if src_dest.exists() and os.path.getsize(src_dest) == os.path.getsize(args.input):
        print(f"   → {src_dest} (already present, skip)")
    elif os.path.abspath(args.input) != os.path.abspath(src_dest):
        shutil.copy2(args.input, src_dest)
        print(f"   → {src_dest} (original source)")

    # Write metadata to inputs/
    src_basename = os.path.basename(args.input)
    metadata = {
        "source_file": os.path.abspath(args.input),
        "source_filename": src_basename,
        "source_format": os.path.splitext(src_basename)[1].lower(),
        "paper_title": pc.title,
        "instruction_files": args.instruction,
        "instructions_dir": args.instructions_dir or "",
        "instruction_context_chars": len(instruction_context),
        "model": args.model or os.environ.get("PAPER2SPEC_MODEL", ""),
        "num_strategies": result.num_detected,
        "strategies": [s.strategy_name for s in result.strategies],
        "version": "0.4.0",
        "layout_version": "nested",
    }
    meta_path = layout.input_path("metadata.json")
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)

    # ── Summary ──
    print(f"\n✅ Analysis complete → {layout.root}/")
    print(f"   Strategies: {result.num_detected}")
    for i, spec in enumerate(result.strategies):
        print(f"   [{i+1}] {spec.strategy_name} ({spec.strategy_type})")
        print(f"       {len(spec.indicators)} indicators, {len(spec.logic_pipeline)} logic steps")

    print(f"\n   Files:")
    print(f"     paper/{src_basename:<24s} — Original document")
    print(f"     inputs/content.md            — Paper content (OCR markdown, single intermediate format)")
    print(f"     inputs/spec.json             — StrategySpec (machine-readable)")
    print(f"     inputs/spec.md               — StrategySpec (human-readable)")
    print(f"     inputs/metadata.json         — Analysis metadata")
    print(f"     config/run_config.yaml       — Per-paper run config (auto-generated from spec.json)")


if __name__ == "__main__":
    main()
