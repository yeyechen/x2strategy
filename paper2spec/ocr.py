"""LightOnOCR-2 inference engine for PDF → markdown extraction.

Uses the ``lightonai/LightOnOCR-2-1B`` 1B-param vision-language model
(Apache 2.0) to render PDF pages as images and extract structured
markdown with HTML tables and LaTeX equations.

Usage::

    from paper2spec.ocr import LightOnOCREngine

    engine = LightOnOCREngine()
    md = engine.extract_pdf("paper.pdf")
    # md is a string containing the full paper as markdown

Caching:
    Output is cached globally at ``<x2strategy>/.cache/<pdf_stem>/ocr_output.md``
    (one folder per paper, keyed by the PDF filename stem).  Subsequent
    calls skip OCR entirely (<0.1s).  Safe to delete ``.cache/`` — it
    will be regenerated on the next run.

Dependencies (optional — import fails gracefully if missing):
    ``transformers >= 5.0.0, pypdfium2, torch >= 2.11, pillow``
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_MODEL_ID = "lightonai/LightOnOCR-2-1B"

# Global cache directory — lives under the x2strategy package root
_CACHE_ROOT = Path(__file__).resolve().parent.parent / ".cache"


class LightOnOCREngine:
    """LightOnOCR-2 inference with global disk caching and GPU/CPU fallback.

    The cache is keyed by the PDF filename stem, so different papers
    get their own cache slot.

    Parameters
    ----------
    force_cpu : bool
        If True, skip GPU detection and use CPU only.
    """

    def __init__(self, force_cpu: bool = False) -> None:
        self._force_cpu = force_cpu
        self._model = None
        self._processor = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def extract_pdf(
        self,
        pdf_path: str | os.PathLike,
        *,
        force: bool = False,
        dpi: int = 200,
    ) -> str:
        """OCR *pdf_path* and return a single markdown string.

        Output is cached globally at ``.cache/<pdf_stem>/ocr_output.md``
        (under the x2strategy package root).

        Parameters
        ----------
        pdf_path:
            Path to the source PDF.
        force:
            If ``True``, re-OCR even when a valid cache exists.
        dpi:
            PDF rendering resolution (default 200 — matches model's
            native ~1540 px for US Letter).

        Returns
        -------
        str
            Full markdown content of the OCR'd paper.
        """
        pdf_path = Path(pdf_path)

        if not pdf_path.is_file():
            raise FileNotFoundError(f"PDF not found: {pdf_path}")

        # Cache keyed by PDF filename
        cache_dir = _CACHE_ROOT / pdf_path.stem
        cache_dir.mkdir(parents=True, exist_ok=True)
        full_md = cache_dir / "ocr_output.md"

        # --- cache hit? --------------------------------------------------
        if not force and full_md.exists():
            logger.info("OCR cache hit for %s", pdf_path.name)
            return full_md.read_text(encoding="utf-8")

        # --- run OCR -----------------------------------------------------
        logger.info("OCR: %s (%s)", pdf_path.name,
                     "CPU" if self._force_cpu else "GPU")
        device, dtype = self._resolve_device()
        self._ensure_model(device, dtype)

        pages_text = self._ocr_pages(pdf_path, dpi, device, dtype)
        combined = "\n\n---\n\n".join(
            f"# Page {i + 1}\n\n{t}" for i, t in enumerate(pages_text)
        )

        full_md.write_text(combined, encoding="utf-8")
        logger.info("OCR done: %d pages → %s", len(pages_text), full_md)
        return combined

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _resolve_device(self) -> tuple[str, str]:
        """Return ``(torch_device, torch_dtype_str)``."""
        if self._force_cpu:
            return "cpu", "float32"

        env_device = os.getenv("PAPER2SPEC_OCR_DEVICE", "auto")
        if env_device != "auto":
            return env_device, "bfloat16"

        try:
            import torch  # type: ignore[import-untyped]
        except ImportError:
            return "cpu", "float32"

        if torch.cuda.is_available():
            # Prefer GPU 1 (GPU 0 is often occupied by vLLM on our box)
            visible = os.environ.get("CUDA_VISIBLE_DEVICES", "")
            if not visible:
                # Try GPU 1 first, fall back to GPU 0
                try:
                    torch.cuda.set_device(1)
                    return "cuda:1", "bfloat16"
                except (RuntimeError, ValueError):
                    return "cuda:0", "bfloat16"
            return "cuda", "bfloat16"

        return "cpu", "float32"

    def _ensure_model(self, device: str, dtype: str) -> None:
        """Lazy-load the transformer model + processor."""
        if self._model is not None:
            return

        t0 = time.time()
        import torch  # type: ignore[import-untyped]
        from transformers import (  # type: ignore[import-untyped]
            LightOnOcrForConditionalGeneration,
            LightOnOcrProcessor,
        )

        torch_dtype = torch.bfloat16 if dtype == "bfloat16" else torch.float32
        self._model = LightOnOcrForConditionalGeneration.from_pretrained(
            _MODEL_ID, torch_dtype=torch_dtype
        ).to(device)
        self._model.eval()
        self._processor = LightOnOcrProcessor.from_pretrained(_MODEL_ID)
        logger.info("Model loaded in %.1fs on %s", time.time() - t0, device)

    def _ocr_pages(
        self,
        pdf_path: Path,
        dpi: int,
        device: str,
        dtype: str,
    ) -> list[str]:
        """Render every PDF page and run the model.  Returns per-page text."""
        import torch  # type: ignore[import-untyped]
        import pypdfium2 as pdfium  # type: ignore[import-untyped]

        pdf = pdfium.PdfDocument(str(pdf_path))
        n_pages = len(pdf)
        scale = dpi / 72.0
        t_start = time.time()
        results: list[str] = []

        for page_ix in range(n_pages):
            page = pdf[page_ix]
            image = page.render(scale=scale).to_pil()

            conversation = [{
                "role": "user",
                "content": [{"type": "image", "image": image}],
            }]

            inputs = self._processor.apply_chat_template(  # type: ignore[union-attr]
                conversation,
                add_generation_prompt=True,
                tokenize=True,
                return_dict=True,
                return_tensors="pt",
            )
            inputs = {
                k: (
                    v.to(device=device, dtype=torch.bfloat16)
                    if v.is_floating_point()
                    else v.to(device)
                )
                for k, v in inputs.items()
            }

            t_page = time.time()
            with torch.no_grad():
                output_ids = self._model.generate(  # type: ignore[union-attr]
                    **inputs, max_new_tokens=4096
                )
            gen_time = time.time() - t_page

            text = self._processor.decode(  # type: ignore[union-attr]
                output_ids[0, inputs["input_ids"].shape[1]:],
                skip_special_tokens=True,
            )
            results.append(text)
            logger.info(
                "page %d/%d in %.1fs (total %.1fs)",
                page_ix + 1, n_pages, gen_time, time.time() - t_start,
            )

        pdf.close()
        return results


def ocr_pdf(
    pdf_path: str | os.PathLike,
    *,
    force: bool = False,
    dpi: int = 200,
    force_cpu: bool = False,
) -> str:
    """One-shot OCR of *pdf_path* → markdown string.

    Thin wrapper around :class:`LightOnOCREngine` for the most common
    one-shot use case.
    """
    return LightOnOCREngine(force_cpu=force_cpu).extract_pdf(
        pdf_path, force=force, dpi=dpi,
    )


__all__ = ["LightOnOCREngine", "ocr_pdf"]
