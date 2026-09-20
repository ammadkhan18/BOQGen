"""
OCR wrapper around EasyOCR.

EasyOCR (PyTorch-based) is somewhat heavy for a free Streamlit Cloud
instance, so this module is written to fail SOFT: if the model can't be
loaded (missing dependency, low memory, cold-start timeout on first run),
the rest of the app keeps working - it just proceeds without the OCR text
hint, relying on the vision LLM alone. This is surfaced to the user as a
small notice, never a crash.

OCR output is used only as an EXTRA hint string appended to the AI prompt
(e.g. "OCR read: SLAB THK 125mm, COL 230x450, FOOTING F1 1.2x1.2x0.3").
It is never used for calculations directly.
"""
from __future__ import annotations

import logging
from functools import lru_cache
from typing import List, Tuple

from PIL import Image

logger = logging.getLogger(__name__)

_OCR_AVAILABLE = True
try:
    import easyocr  # noqa: F401
except Exception:  # pragma: no cover - environment dependent
    _OCR_AVAILABLE = False


@lru_cache(maxsize=1)
def _get_reader():
    import easyocr

    # English only for the MVP; GPU disabled to stay within free-tier CPU.
    return easyocr.Reader(["en"], gpu=False, verbose=False)


def ocr_available() -> bool:
    return _OCR_AVAILABLE


def extract_text_regions(image: Image.Image, min_confidence: float = 0.35) -> List[Tuple[str, float]]:
    """Return a list of (text, confidence) tuples detected in the image.

    Returns an empty list (never raises) if OCR is unavailable or fails,
    so callers don't need defensive try/except at every call site.
    """
    if not _OCR_AVAILABLE:
        return []
    try:
        import numpy as np

        reader = _get_reader()
        arr = np.array(image.convert("RGB"))
        raw_results = reader.readtext(arr)
        out: List[Tuple[str, float]] = []
        for _bbox, text, conf in raw_results:
            if conf >= min_confidence and text.strip():
                out.append((text.strip(), float(conf)))
        return out
    except Exception as exc:  # pragma: no cover
        logger.warning("OCR extraction failed, continuing without it: %s", exc)
        return []


def build_ocr_hint_text(image: Image.Image, max_items: int = 40) -> str:
    """Build a compact human-readable string of OCR'd fragments to feed the LLM."""
    regions = extract_text_regions(image)
    if not regions:
        return ""
    regions = sorted(regions, key=lambda r: -r[1])[:max_items]
    fragments = [text for text, _conf in regions]
    return "OCR-detected text fragments (may include noise): " + " | ".join(fragments)
