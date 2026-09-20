"""
Lightweight OpenCV-based image cleanup for uploaded PNG/JPG drawings
(and rasterized PDF pages).

Kept intentionally simple for the MVP: contrast normalization, mild
denoising, and a bounded resize. No attempt at full CAD vectorization
or automatic wall/room detection in this version (see README roadmap).
"""
from __future__ import annotations

import cv2
import numpy as np
from PIL import Image


def pil_to_cv2(img: Image.Image) -> np.ndarray:
    arr = np.array(img.convert("RGB"))
    return cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)


def cv2_to_pil(arr: np.ndarray) -> Image.Image:
    rgb = cv2.cvtColor(arr, cv2.COLOR_BGR2RGB)
    return Image.fromarray(rgb)


def clean_drawing_image(img: Image.Image, max_dimension: int = 1600) -> Image.Image:
    """Normalize contrast, denoise lightly, and cap the longest side.

    Architectural line drawings are typically high-contrast black-on-white,
    so we boost contrast slightly and reduce scanner noise/speckle without
    destroying thin dimension lines and text.
    """
    cv_img = pil_to_cv2(img)

    # Mild denoise (preserves edges/lines better than a plain blur)
    cv_img = cv2.fastNlMeansDenoisingColored(cv_img, None, 5, 5, 7, 21)

    # Contrast normalization via CLAHE on the luminance channel
    lab = cv2.cvtColor(cv_img, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    l = clahe.apply(l)
    cv_img = cv2.cvtColor(cv2.merge((l, a, b)), cv2.COLOR_LAB2BGR)

    result = cv2_to_pil(cv_img)

    # Bound the longest side to keep the payload sent to the LLM reasonable
    w, h = result.size
    longest = max(w, h)
    if longest > max_dimension:
        scale = max_dimension / longest
        result = result.resize((int(w * scale), int(h * scale)), Image.LANCZOS)

    return result


def estimate_is_drawing_like(img: Image.Image) -> bool:
    """Cheap heuristic sanity check: is this plausibly a line drawing (as
    opposed to e.g. a photo of a person, a blank page, or a random JPEG)?
    Used only to show a friendly warning, never to hard-block the upload.
    """
    cv_img = pil_to_cv2(img)
    gray = cv2.cvtColor(cv_img, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 50, 150)
    edge_ratio = float(np.count_nonzero(edges)) / edges.size
    # Line drawings tend to have a modest but non-trivial edge density.
    return 0.005 < edge_ratio < 0.35
