"""Blur detection utilities."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

import numpy as np

try:
    import cv2  # type: ignore
except ImportError:  # pragma: no cover - fallback for environments without OpenCV
    from . import cv2_stub as cv2  # type: ignore

MAX_LONG_SIDE = 1024


def preprocess_gray(img_bgr: np.ndarray, long_side: int = MAX_LONG_SIDE) -> np.ndarray:
    """Convert *img_bgr* to grayscale and resize the long side to ``long_side``.

    Parameters
    ----------
    img_bgr:
        Image array in BGR or grayscale format.
    long_side:
        Target size for the longest image edge. Values smaller than the current
        long side keep the image unchanged.

    Returns
    -------
    np.ndarray
        Preprocessed 8-bit grayscale image.
    """

    if img_bgr is None:
        raise ValueError("img_bgr must not be None")

    if img_bgr.ndim == 3:
        gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    elif img_bgr.ndim == 2:
        gray = img_bgr
    else:
        raise ValueError("Unsupported image shape for preprocessing")

    if gray.dtype != np.float32:
        gray = gray.astype(np.float32, copy=False)

    h, w = gray.shape[:2]
    long_dim = max(h, w)
    if long_dim > long_side and long_dim > 0:
        scale = long_side / float(long_dim)
        new_w = max(1, int(round(w * scale)))
        new_h = max(1, int(round(h * scale)))
        gray = cv2.resize(gray, (new_w, new_h), interpolation=cv2.INTER_AREA)

    # Ensure 8-bit range using convertScaleAbs to avoid underflow on dark frames
    gray = cv2.convertScaleAbs(gray)
    return gray


def laplacian_variance(gray: np.ndarray) -> float:
    """Return the variance of the Laplacian for a preprocessed grayscale image."""
    if gray.size == 0:
        return 0.0
    lap = cv2.Laplacian(gray, cv2.CV_64F, ksize=3)
    return float(lap.var())


def blur_score(img_bgr: np.ndarray, long_side: int = MAX_LONG_SIDE) -> float:
    """Compute a blur score using the Laplacian variance of a BGR image."""
    gray = preprocess_gray(img_bgr, long_side=long_side)
    return laplacian_variance(gray)


@dataclass
class BlurResult:
    """Container holding blur score and the associated grayscale image."""

    gray: np.ndarray
    score: float


def compute_blur_with_gray(img_bgr: np.ndarray, long_side: int = MAX_LONG_SIDE) -> BlurResult:
    """Return a :class:`BlurResult` containing grayscale data and blur score."""
    gray = preprocess_gray(img_bgr, long_side=long_side)
    return BlurResult(gray=gray, score=laplacian_variance(gray))
