"""Simple PDF text extraction (PyMuPDF plain-text fallback).

For the primary PDF → markdown pipeline, see ``paper2spec.ocr``
(LightOnOCR-2 inference engine).

This module provides a lightweight fallback used when LightOnOCR-2
is unavailable (missing deps, no GPU, or PDF corruption).
"""

import logging
import os

import fitz  # PyMuPDF

logger = logging.getLogger(__name__)


class PDFExtractor:
    """Simple PyMuPDF text extraction (fallback only)."""

    @staticmethod
    def extract_text(pdf_path: str) -> str:
        """Return plain text from every page of *pdf_path*."""
        if not os.path.isfile(pdf_path):
            raise FileNotFoundError(f"PDF not found: {pdf_path}")

        doc = fitz.open(pdf_path)
        texts: list[str] = []
        for i in range(len(doc)):
            page_text = doc[i].get_text()
            if page_text.strip():
                texts.append(page_text)
        doc.close()

        result = "\n\n".join(texts)
        logger.info("fitz text extraction: %d pages → %d chars", len(texts), len(result))
        return result
