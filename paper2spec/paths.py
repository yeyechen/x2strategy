"""Per-paper directory layout — single source of truth.

Every paper replication lives under ``PAPER2SPEC_REPLICATIONS_PATH/<slug>/``
and has the same nested structure:

    <slug>/
    ├── README.md
    ├── paper/                 # source PDF (large; usually gitignored per-paper)
    ├── inputs/                # paper2spec artifacts (parse + extract + metadata)
    ├── diagnostics/           # mid-pipeline debug artifacts
    ├── src/                   # generated strategy code (strategy.py)
    ├── data/                  # parquet caches (gitignored per-paper)
    ├── results/               # spec2code outputs (metrics, plots, diagnosis)
    │   └── key_pred/          # one CSV + PNG per key observable factor
    └── config/                # optional run config

Both the paper2spec CLI scripts and the LLM-generated ``strategy.py`` MUST
use :func:`paper_layout` rather than hardcoding ``os.path.join`` paths —
that's what keeps the contract enforceable.

Usage::

    from paper2spec.paths import paper_layout

    layout = paper_layout("ssrn_1262416")        # default replications path
    layout.ensure()                               # mkdir -p all dirs
    layout.input_path("spec.json")                # → <root>/inputs/spec.json
    layout.src_path("strategy.py")                # → <root>/src/strategy.py
    layout.result_path("metrics.json")            # → <root>/results/metrics.json

Why this exists: the previous flat layout (content.json, spec.json,
strategy_1.py, data_match_report.json all siblings at the per-paper root)
was hard to navigate, made standalone-repo publication awkward, and gave
no visual distinction between inputs and outputs. This module is the
contract that fixes all three.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

from paper2spec.config import get_replications_path


# Subdirectory names — kept as module constants so they're searchable
# (``grep PAPER_DIR x2strategy/``) and so refactors don't require touching
# call sites.
PAPER_DIR = "paper"
INPUTS_DIR = "inputs"
DIAGNOSTICS_DIR = "diagnostics"
SRC_DIR = "src"
DATA_DIR = "data"
RESULTS_DIR = "results"
KEY_PRED_DIR = "key_pred"
CONFIG_DIR = "config"
LOGS_DIR = "logs"


def _slugify(text: str) -> str:
    """Convert a title / filename into a filesystem-safe slug.

    Same heuristic the legacy code used (``paper2spec/scripts/analyze.py``
    ``_slugify``): lowercase, strip punctuation, collapse separators.
    """
    text = (text or "").lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[-\s]+", "_", text)
    return text[:80].rstrip("_") or "paper"


@dataclass(frozen=True)
class PaperLayout:
    """Resolved paths for one paper replication.

    Construct via :func:`paper_layout` (handles replications-root resolution
    and slug normalization). Direct construction is allowed but unusual.
    """

    slug: str
    root: Path
    paper_dir: Path
    inputs_dir: Path
    diagnostics_dir: Path
    src_dir: Path
    data_dir: Path
    results_dir: Path
    key_pred_dir: Path
    config_dir: Path
    logs_dir: Path

    # ── Construction helpers ───────────────────────────────────────────────

    def ensure(self) -> "PaperLayout":
        """Create all subdirectories (idempotent). Returns self for chaining."""
        for d in (
            self.paper_dir,
            self.inputs_dir,
            self.diagnostics_dir,
            self.src_dir,
            self.data_dir,
            self.results_dir,
            self.key_pred_dir,
            self.config_dir,
            self.logs_dir,
        ):
            d.mkdir(parents=True, exist_ok=True)
        return self

    # ── Path builders ──────────────────────────────────────────────────────
    #
    # These are the canonical ways to construct output paths inside a paper
    # folder. Use them everywhere instead of ``os.path.join(self.root, ...)``.

    def input_path(self, name: str) -> Path:
        """Path under inputs/ — paper2spec artifacts (content, spec, metadata)."""
        return self.inputs_dir / name

    def diagnostic_path(self, name: str) -> Path:
        """Path under diagnostics/ — mid-pipeline debug artifacts."""
        return self.diagnostics_dir / name

    def src_path(self, name: str) -> Path:
        """Path under src/ — generated strategy code."""
        return self.src_dir / name

    def data_path(self, name: str) -> Path:
        """Path under data/ — parquet caches."""
        return self.data_dir / name

    def result_path(self, name: str) -> Path:
        """Path under results/ — backtest outputs."""
        return self.results_dir / name

    def key_pred_path(self, name: str) -> Path:
        """Path under results/key_pred/ — per-factor CSVs/PNGs."""
        return self.key_pred_dir / name

    def config_path(self, name: str) -> Path:
        """Path under config/ — optional run config."""
        return self.config_dir / name

    def paper_pdf_path(self, name: str = "original.pdf") -> Path:
        """Path under paper/ — the source PDF."""
        return self.paper_dir / name

    def log_path(self, name: str) -> Path:
        """Path under logs/ — runtime log files (agent_run.log, run.log, …)."""
        return self.logs_dir / name


def paper_layout(
    slug: str | None = None,
    *,
    replications_root: str | os.PathLike[str] | None = None,
) -> PaperLayout:
    """Resolve a :class:`PaperLayout` for one paper.

    Args:
        slug: paper slug (filesystem-safe identifier). If ``None``, defaults
            to ``"default"`` — usually wrong, callers should pass an explicit
            slug.
        replications_root: override ``PAPER2SPEC_REPLICATIONS_PATH`` for
            this call. Useful in tests. If relative, resolved against
            ``cwd``.

    Returns:
        A :class:`PaperLayout` rooted at ``<replications_root>/<slug>/``.
    """
    if replications_root is None:
        root_base = Path(get_replications_path())
    else:
        root_base = Path(os.path.expanduser(os.fspath(replications_root)))
        if not root_base.is_absolute():
            root_base = (Path.cwd() / root_base).resolve()

    slug = _slugify(slug or "default")
    root = root_base / slug
    return PaperLayout(
        slug=slug,
        root=root,
        paper_dir=root / PAPER_DIR,
        inputs_dir=root / INPUTS_DIR,
        diagnostics_dir=root / DIAGNOSTICS_DIR,
        src_dir=root / SRC_DIR,
        data_dir=root / DATA_DIR,
        results_dir=root / RESULTS_DIR,
        key_pred_dir=root / RESULTS_DIR / KEY_PRED_DIR,
        config_dir=root / CONFIG_DIR,
        logs_dir=root / LOGS_DIR,
    )


def paper_layout_from_pdf(pdf_path: str | os.PathLike[str]) -> PaperLayout:
    """Resolve a layout using the PDF's filename as the slug.

    Mirrors the legacy ``scripts/parse.py`` behavior of using
    ``Path(pdf).stem`` as the slug when one isn't supplied.
    """
    stem = Path(pdf_path).stem
    return paper_layout(slug=stem)


__all__ = [
    "PAPER_DIR",
    "INPUTS_DIR",
    "DIAGNOSTICS_DIR",
    "SRC_DIR",
    "DATA_DIR",
    "RESULTS_DIR",
    "KEY_PRED_DIR",
    "CONFIG_DIR",
    "PaperLayout",
    "paper_layout",
    "paper_layout_from_pdf",
]