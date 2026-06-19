"""PDF text extraction with hybrid strategy.

Uses pymupdf4llm (Markdown output) for normal pages, falls back to
PyMuPDF plain-text for pages with excessive vector drawings.
"""

import logging
import os
import time

import fitz  # PyMuPDF
import pymupdf4llm

logger = logging.getLogger(__name__)

# Pages with more drawing commands than this use fitz plain-text fallback.
DRAWING_THRESHOLD = 10_000

# Engineering decision #9: truncate oversized PDFs (first N + last M pages).
MAX_FRONT_PAGES = 50
MAX_BACK_PAGES = 10


class PDFExtractor:
    """Extract text and tables from PDF, handling heavy-drawing pages gracefully."""

    @staticmethod
    def extract_text(pdf_path: str) -> str:
        """Return full paper text from *pdf_path*."""
        if not os.path.isfile(pdf_path):
            raise FileNotFoundError(f"PDF not found: {pdf_path}")
        return PDFExtractor._extract_hybrid(pdf_path)

    @staticmethod
    def extract_tables(pdf_path: str) -> list[list[list[str]]]:
        """Extract all tables from a PDF using PyMuPDF's table detection.

        Uses ``strategy=\"text\"`` to handle LaTeX booktabs-style tables
        (common in academic papers), then filters to keep only tables
        containing numeric data (digits and decimal numbers).

        Returns a list of tables.  Each table is a list of rows.
        Each row is a list of cleaned cell strings.
        """
        import re

        if not os.path.isfile(pdf_path):
            raise FileNotFoundError(f"PDF not found: {pdf_path}")

        doc = fitz.open(pdf_path)
        all_tables: list[list[list[str]]] = []
        for i in range(doc.page_count):
            tf = doc[i].find_tables(strategy="text")
            if not tf or not tf.tables:
                continue
            for table in tf.tables:
                # Use to_markdown() for clean output AND for filter check
                md = table.to_markdown()
                if not PDFExtractor._is_data_table_md(md):
                    continue
                grid = PDFExtractor._markdown_to_grid(md)
                if grid:
                    all_tables.append(grid)

        page_count = doc.page_count
        doc.close()
        logger.info(
            "Extracted %d tables from %d pages", len(all_tables), page_count
        )
        return all_tables

    @staticmethod
    def _is_data_table_md(md: str) -> bool:
        """Heuristic: real data tables have numeric cell content."""
        import re
        # Count lines with digits
        lines = md.split("\n")
        digit_lines = sum(1 for l in lines if re.search(r"\d", l))
        # Must have clean decimal numbers (to_markdown() produces them)
        has_decimal = bool(re.search(r"\d+\.\d+", md))
        # At least 3 rows in a markdown table
        row_count = sum(1 for l in lines if l.strip().startswith("|")
                       and not all(c in "|-: " for c in l.strip()))
        return digit_lines >= 3 and has_decimal and row_count >= 3

    @staticmethod
    def _markdown_to_grid(md: str) -> list[list[str]]:
        """Parse a Markdown table string back into a list-of-lists grid."""
        grid: list[list[str]] = []
        for line in md.split("\n"):
            line = line.strip()
            if not line.startswith("|"):
                continue
            # Skip separator rows like |---|---|
            if all(c in "|-: " for c in line):
                continue
            cells = [c.strip() for c in line.split("|")]
            if cells and cells[0] == "":
                cells = cells[1:]
            if cells and cells[-1] == "":
                cells = cells[:-1]
            if cells:
                grid.append(cells)
        return grid

    @staticmethod
    def _extract_hybrid(pdf_path: str) -> str:
        start = time.time()
        doc = fitz.open(pdf_path)
        total = len(doc)

        # Determine which pages to process (truncation for oversized PDFs)
        if total > MAX_FRONT_PAGES + MAX_BACK_PAGES:
            front = list(range(MAX_FRONT_PAGES))
            back = list(range(total - MAX_BACK_PAGES, total))
            pages_to_process = front + back
            logger.info(
                "Truncating %d-page PDF → first %d + last %d pages",
                total, MAX_FRONT_PAGES, MAX_BACK_PAGES,
            )
        else:
            pages_to_process = list(range(total))

        # Classify pages: heavy-drawing vs normal
        heavy_pages: list[int] = []
        normal_pages: list[int] = []
        for i in pages_to_process:
            drawings = doc[i].get_drawings()
            if len(drawings) > DRAWING_THRESHOLD:
                heavy_pages.append(i)
            else:
                normal_pages.append(i)
        doc.close()

        page_texts: dict[int, str] = {}

        # Heavy-drawing pages → fitz plain text
        if heavy_pages:
            logger.info("Heavy-drawing pages (%d): using fitz fallback", len(heavy_pages))
            doc = fitz.open(pdf_path)
            for i in heavy_pages:
                page_texts[i] = doc[i].get_text()
            doc.close()

        # Normal pages → pymupdf4llm markdown (batch)
        if normal_pages:
            md_pages = pymupdf4llm.to_markdown(pdf_path, pages=normal_pages, page_chunks=True)
            for chunk in md_pages:
                # pymupdf4llm uses 1-indexed page_number
                page_num = chunk["metadata"]["page_number"] - 1
                page_texts[page_num] = chunk["text"]

        # Combine in page order
        combined = "\n\n".join(page_texts[i] for i in sorted(page_texts))
        elapsed = time.time() - start
        logger.info("PDF extracted: %d pages, %d chars, %.1fs", len(page_texts), len(combined), elapsed)
        return combined
