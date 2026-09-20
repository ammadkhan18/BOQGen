"""
PDF ingestion using PyMuPDF (fitz).

Responsibilities:
- Render each PDF page to a PIL image at a reasonable DPI for the vision LLM
- Pull any embedded/selectable text layer (some architectural PDFs export
  dimension text as real text, not just vector lines) as a free bonus signal
  for the AI extraction prompt.

Does NOT do any AI or engineering logic - purely mechanical extraction.
"""
from __future__ import annotations

import io
from dataclasses import dataclass, field
from typing import List

try:
    import pymupdf as fitz  # PyMuPDF >= 1.24 preferred import name
except ImportError:  # pragma: no cover
    import fitz  # fallback for older PyMuPDF versions
from PIL import Image


@dataclass
class PdfPage:
    page_number: int
    image: Image.Image
    text: str = ""


@dataclass
class PdfExtractionResult:
    pages: List[PdfPage] = field(default_factory=list)

    @property
    def combined_text(self) -> str:
        return "\n".join(f"--- Page {p.page_number} ---\n{p.text}" for p in self.pages if p.text.strip())


def process_pdf(file_bytes: bytes, dpi: int = 200, max_pages: int = 5) -> PdfExtractionResult:
    """Render up to `max_pages` pages of a PDF to images + extract text layer.

    Args:
        file_bytes: raw PDF bytes as uploaded via Streamlit's file_uploader
        dpi: rendering resolution. 150-220 is a good tradeoff for LLM vision
             input (higher doesn't meaningfully help and bloats payload size).
        max_pages: safety cap so a huge PDF doesn't blow up the free-tier
             LLM context / rate limits.
    """
    result = PdfExtractionResult()
    doc = fitz.open(stream=file_bytes, filetype="pdf")
    try:
        zoom = dpi / 72.0
        matrix = fitz.Matrix(zoom, zoom)
        for i, page in enumerate(doc):
            if i >= max_pages:
                break
            pix = page.get_pixmap(matrix=matrix, alpha=False)
            img = Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")
            text = page.get_text("text") or ""
            result.pages.append(PdfPage(page_number=i + 1, image=img, text=text))
    finally:
        doc.close()
    return result
