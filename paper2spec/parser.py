"""Paper parser — Document → PaperContent.

Supported formats: PDF (via LightOnOCR-2), Markdown (.md), DOCX, plain text.

For PDFs, the parser uses LightOnOCR-2 (a 1B-param vision-language model)
to produce clean markdown with HTML tables and LaTeX equations.

The LLM extraction step (methodology / data_description / signal_logic)
has been moved to the extractor stage — the parser now produces a single
content.md (markdown) that the extractor reads directly.
"""

import asyncio
import logging
import os
import re
from pathlib import Path
from typing import Optional

from paper2spec.models import PaperContent

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════
# Public API
# ══════════════════════════════════════════════════════════════════


def parse_pdf(
    pdf_path: str,
    *,
    force_ocr: bool = False,
    model: Optional[str] = None,  # kept for backward compat, unused
) -> PaperContent:
    """PDF path → PaperContent.

    Uses LightOnOCR-2 for markdown extraction with HTML tables and
    LaTeX equations.  Cache is automatic (global, keyed by PDF hash).

    Args:
        pdf_path: Path to the PDF file.
        force_ocr: If True, re-OCR even when cache exists.
        model: Deprecated — kept for backward compat.
    """
    return asyncio.run(aparse_pdf(pdf_path, force_ocr=force_ocr))


async def aparse_pdf(
    pdf_path: str,
    *,
    force_ocr: bool = False,
) -> PaperContent:
    """Async: PDF path → PaperContent (OCR, no LLM calls).

    Args:
        pdf_path: Path to the PDF.
        force_ocr: Force re-OCR even if cached.
    """
    logger.info("Parsing PDF: %s", pdf_path)

    from paper2spec.ocr import LightOnOCREngine

    engine = LightOnOCREngine()
    content_md = engine.extract_pdf(pdf_path, force=force_ocr)
    logger.info("OCR extracted %d chars from %s", len(content_md), pdf_path)

    return _populate_paper_content(content_md, source=pdf_path)


def parse_text(text: str, *, source: str = "text") -> PaperContent:
    """Raw text → PaperContent (no LLM calls)."""
    return _populate_paper_content(text, source=source)


def parse_markdown(md_path: str) -> PaperContent:
    """Markdown file → PaperContent (no LLM calls)."""
    logger.info("Parsing Markdown: %s", md_path)
    with open(md_path, "r", encoding="utf-8") as f:
        content_md = f.read()
    logger.info("Read %d chars from Markdown", len(content_md))
    return _populate_paper_content(content_md, source=md_path)


def parse_docx(docx_path: str) -> PaperContent:
    """DOCX file → PaperContent (no LLM calls). Requires python-docx."""
    return asyncio.run(aparse_docx(docx_path))


async def aparse_docx(docx_path: str) -> PaperContent:
    """Async: DOCX file → PaperContent (no LLM calls)."""
    logger.info("Parsing DOCX: %s", docx_path)
    try:
        import docx
    except ImportError as e:
        raise ImportError(
            "DOCX support requires: pip install python-docx  "
            "(or: uv sync --extra docx)"
        ) from e

    doc = await asyncio.to_thread(docx.Document, docx_path)
    paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
    full_text = "\n\n".join(paragraphs)
    logger.info(
        "Extracted %d chars from DOCX (%d paragraphs)",
        len(full_text), len(paragraphs),
    )
    return _populate_paper_content(full_text, source=docx_path)


async def aparse_markdown(md_path: str) -> PaperContent:
    """Async: Markdown file → PaperContent."""
    logger.info("Parsing Markdown: %s", md_path)
    with open(md_path, "r", encoding="utf-8") as f:
        content_md = f.read()
    logger.info("Read %d chars", len(content_md))
    return _populate_paper_content(content_md, source=md_path)


_FORMAT_DISPATCH = {
    ".pdf": aparse_pdf,
    ".md": aparse_markdown,
    ".markdown": aparse_markdown,
    ".docx": aparse_docx,
    ".txt": None,  # handled specially
}


def parse_document(path: str) -> PaperContent:
    """Sync: auto-detect format from extension and parse."""
    return asyncio.run(aparse_document(path))


async def aparse_document(path: str) -> PaperContent:
    """Async: auto-detect format from extension and parse."""
    ext = os.path.splitext(path)[1].lower()
    if ext not in _FORMAT_DISPATCH:
        raise ValueError(
            f"Unsupported file format '{ext}'. "
            f"Supported: {', '.join(sorted(_FORMAT_DISPATCH.keys()))}"
        )
    if ext == ".txt":
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
        return _populate_paper_content(text, source=path)
    handler = _FORMAT_DISPATCH[ext]
    return await handler(path)


# ══════════════════════════════════════════════════════════════════
# Internals
# ══════════════════════════════════════════════════════════════════


def _populate_paper_content(content_md: str, *, source: str = "text") -> PaperContent:
    """Build a PaperContent from raw markdown (no LLM calls).

    The extractor stage later reads ``pc.full_text`` as the single
    source of truth.  Title and abstract are extracted heuristically;
    methodology / data_description / signal_logic are left empty.
    """
    pc = PaperContent(full_text=content_md)
    pc.title = _extract_title(source, content_md)
    pc.abstract = _extract_abstract(content_md)
    return pc


def _extract_title(source: str, full_text: str) -> str:
    """Heuristic: first H1 heading in the markdown, skipping ``# Page N`` markers."""
    for line in full_text[:2000].splitlines():
        m = re.match(r"^#\s+(.+?)$", line)
        if m:
            candidate = m.group(1).strip()
            # Skip the per-page marker that the OCR engine inserts.
            if not re.match(r"^Page\s+\d+$", candidate):
                return candidate
    return os.path.basename(source).replace(".pdf", "").replace("_", " ")


def _extract_abstract(full_text: str) -> str:
    """Heuristic: text between '# Abstract' and next heading, or first 1500 chars."""
    m = re.search(
        r"(?:^|\n)#*\s*Abstract\s*\n+(.*?)(?:\n#{1,3}\s+|\n\n[A-Z])",
        full_text[:3000],
        re.IGNORECASE | re.DOTALL,
    )
    if m:
        return m.group(1).strip()
    return full_text[:1500]
