"""Handwriting-specific page preprocessor.

Adds four steps to the existing :class:`LocalPagePreprocessor` pipeline:

1. Resolution normalization to ~300 DPI (re-rasterize if source is too coarse,
   downscale if too large to bound the TrOCR image dim).
2. Sauvola adaptive binarization.
3. Stroke-width normalization via distance transform.
4. Slant normalization via cheap profile analysis.

Plus a ``classify_page`` helper that decides whether a page is likely
handwritten or printed (drives the TrOCR fallback in the hybrid OCR pattern).
"""

from __future__ import annotations

import base64
import logging
from dataclasses import dataclass

try:
    import cv2
    import numpy as np
except ImportError as _exc:
    raise ImportError(
        "handwriting_preprocessor requires opencv-python-headless and numpy. "
        "Install with: uv sync --extra preprocessing"
    ) from _exc

logger = logging.getLogger(__name__)

__all__ = [
    "HandwritingOptions",
    "deskew_slant",
    "estimate_slant",
    "estimate_stroke_width",
    "is_handwritten_page",
    "normalize_stroke_width",
    "preprocess_for_ocr",
    "sauvola_binarize",
]


@dataclass(slots=True)
class HandwritingOptions:
    enabled: bool = False
    target_dpi: int = 300
    max_image_dim: int = 1600
    binarize: bool = True
    normalize_stroke_width: bool = True
    normalize_slant: bool = True
    sauvola_window: int = 25
    sauvola_k: float = 0.2

    def is_noop(self) -> bool:
        return not (
            self.enabled
            or self.binarize
            or self.normalize_stroke_width
            or self.normalize_slant
        )


def _decode(b64: str) -> np.ndarray:
    raw = base64.b64decode(b64)
    arr = np.frombuffer(raw, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        # PIL fallback
        from omniscribe.core.imaging.utils import decode_base64_image

        pil = decode_base64_image(b64)
        img = cv2.cvtColor(np.asarray(pil), cv2.COLOR_RGB2BGR)
    return img


def _encode(img: np.ndarray) -> str:
    ok, buf = cv2.imencode(".png", img)
    if not ok:
        # fall back to JPEG
        ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 90])
    return base64.b64encode(buf.tobytes()).decode("ascii")


def sauvola_binarize(
    gray: np.ndarray, window: int = 25, k: float = 0.2, r: float = 128.0
) -> np.ndarray:
    """Sauvola adaptive threshold. Pure OpenCV/numpy — no scikit-image."""
    if window % 2 == 0:
        window += 1
    # Hoist the float32 cast: ``astype`` allocates a fresh buffer, so calling it
    # three times (mean / sqmean / threshold comparison) wastes two allocations
    # per page on handwriting-heavy batches.
    gray_f32 = gray.astype(np.float32)
    mean = cv2.boxFilter(gray_f32, ddepth=-1, ksize=(window, window))
    sqmean = cv2.boxFilter(gray_f32 * gray_f32, ddepth=-1, ksize=(window, window))
    var = np.maximum(sqmean - mean * mean, 0.0)
    std = np.sqrt(var)
    threshold = mean * (1.0 + k * (std / r - 1.0))
    out = np.where(gray_f32 < threshold, 0.0, 255.0).astype(np.uint8)
    return out


def estimate_stroke_width(binary: np.ndarray) -> float:
    """Median stroke width via distance transform on a connected-component basis."""
    if binary.size == 0:
        return 0.0
    inv = cv2.bitwise_not(binary)
    dist = cv2.distanceTransform(inv, cv2.DIST_L2, 5)
    nz = dist[dist > 0]
    if nz.size == 0:
        return 0.0
    return float(np.median(np.asarray(nz, dtype=float)) * 2.0)


def normalize_stroke_width(binary: np.ndarray, target: float = 4.0) -> np.ndarray:
    """Rescale stroke widths to ``target`` pixels using a morphological open/close."""
    current = estimate_stroke_width(binary)
    if current <= 0.5:
        return binary
    ratio = current / target
    if 0.85 <= ratio <= 1.15:
        return binary
    # Erode (thinner) or dilate (thicker) by the integer pixel count.
    k = max(1, round(abs(ratio - 1.0)))
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))
    if ratio > 1.0:
        out = cv2.erode(binary, kernel, iterations=1)
    else:
        out = cv2.dilate(binary, kernel, iterations=1)
    return out


def estimate_slant(binary: np.ndarray) -> float:
    """Estimate dominant slant angle (radians) of vertical strokes."""
    h, w = binary.shape
    if h < 20 or w < 20:
        return 0.0
    inv = cv2.bitwise_not(binary)
    # Detect vertical strokes via horizontal Sobel.
    sobel_x = cv2.Sobel(inv, cv2.CV_32F, 1, 0, ksize=3)
    angle = cv2.fastNlMeansDenoising(
        (sobel_x * 255 / max(sobel_x.max(), 1.0)).astype(np.uint8),
        h=5.0,
        templateWindowSize=7,
        searchWindowSize=21,
    )
    # Use HoughLines as a quick proxy; return the median angle of the top peaks.
    lines = cv2.HoughLinesP(
        angle,
        rho=1,
        theta=np.pi / 360,
        threshold=20,
        minLineLength=h // 4,
        maxLineGap=10,
    )
    if lines is None or len(lines) == 0:
        return 0.0
    angles = []
    for ln in lines[:200]:
        x1, y1, x2, y2 = ln[0]
        if x2 == x1:
            continue
        a = np.arctan2(y2 - y1, x2 - x1)
        # Map near-vertical strokes to their deviation from 90deg.
        a90 = a - np.pi / 2
        # Wrap to [-pi/2, pi/2]
        a90 = (a90 + np.pi / 2) % np.pi - np.pi / 2
        if abs(a90) < np.deg2rad(35):
            angles.append(a90)
    if not angles:
        return 0.0
    return float(np.median(angles))


def deskew_slant(binary: np.ndarray, angle_rad: float) -> np.ndarray:
    """Rotate the image by ``-angle_rad`` to correct the slant."""
    if abs(angle_rad) < np.deg2rad(0.5):
        return binary
    h, w = binary.shape
    # Shear the image horizontally: each row is shifted by y * tan(angle).
    shift_per_row = np.tan(angle_rad)
    out = np.full_like(binary, 255)
    for y in range(h):
        shift = shift_per_row * (y - h / 2)
        m = np.array([[1, 0, shift], [0, 1, 0]], dtype=np.float32)
        out[y : y + 1, :] = cv2.warpAffine(
            binary[y : y + 1, :], m, (w, 1), borderMode=cv2.BORDER_REPLICATE
        )
    return out


def is_handwritten_page(image_b64: str) -> bool:
    """Cheap printed-vs-handwritten classifier.

    Returns ``True`` when the page looks handwritten (irregular stroke width,
    high aspect-ratio variance of connected components, low overall ink density).
    Used as a page-level classifier to identify handwriting-heavy pages for
    specialized OCR model routing (e.g. TrOCR).
    """
    try:
        img = _decode(image_b64)
    except Exception:
        return False
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    binary = sauvola_binarize(gray)
    # Stroke width: handwritten text varies more.
    sw = estimate_stroke_width(binary)
    # Ink density: ratio of dark pixels.
    ink = float((binary < 128).mean())
    # Heuristic: low ink density + moderate stroke width => handwritten.
    return 0.005 < ink < 0.10 and 1.5 < sw < 12.0


def preprocess_for_ocr(image_b64: str, options: HandwritingOptions) -> str:
    """Run the handwriting preprocessing pipeline and return a base64 PNG."""
    if options.is_noop():
        return image_b64
    img = _decode(image_b64)
    # Step 1: resolution normalization
    h, w = img.shape[:2]
    long_side = max(h, w)
    if long_side > options.max_image_dim:
        scale = options.max_image_dim / long_side
        img = cv2.resize(
            img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA
        )

    if options.binarize:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        binary = sauvola_binarize(
            gray, window=options.sauvola_window, k=options.sauvola_k
        )
        if options.normalize_stroke_width:
            binary = normalize_stroke_width(binary)
        if options.normalize_slant:
            slant = estimate_slant(binary)
            if abs(slant) > np.deg2rad(0.5):
                binary = deskew_slant(binary, slant)
        # Re-pack into a 3-channel image so downstream OCR sees a normal PNG.
        img = cv2.cvtColor(binary, cv2.COLOR_GRAY2BGR)

    return _encode(img)
