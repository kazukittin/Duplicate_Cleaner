"""Noise detection metrics."""
from __future__ import annotations

from typing import Dict, Optional

import numpy as np

try:
    import cv2  # type: ignore
except ImportError:  # pragma: no cover - fallback for environments without OpenCV
    from . import cv2_stub as cv2  # type: ignore

from .blur import preprocess_gray

try:  # Optional dependency for wavelet-based metric
    import pywt  # type: ignore
except Exception:  # pragma: no cover - import failure path
    pywt = None  # type: ignore


Percentile = float
NoiseScores = Dict[str, Optional[float]]


def _sobel_magnitude(gray: np.ndarray) -> np.ndarray:
    grad_x = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    grad_y = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    mag = cv2.magnitude(grad_x, grad_y)
    return mag


def _flat_variance(gray: np.ndarray, percentile: Percentile = 60.0) -> float:
    mag = _sobel_magnitude(gray)
    flat_thresh = np.percentile(mag, percentile)
    flat_mask = mag < flat_thresh
    if not np.any(flat_mask):
        return float(np.var(gray.astype(np.float32)))
    flat_pixels = gray[flat_mask].astype(np.float32)
    return float(np.var(flat_pixels))


def _jpeg_blockiness(gray: np.ndarray) -> float:
    gray_f = gray.astype(np.float32, copy=False)
    h, w = gray_f.shape
    diffs = []

    if w > 8:
        right = gray_f[:, 8::8]
        left = gray_f[:, 7::8]
        if right.size and right.shape == left.shape:
            diffs.append(np.abs(right - left))
    if h > 8:
        bottom = gray_f[8::8, :]
        top = gray_f[7::8, :]
        if bottom.size and bottom.shape == top.shape:
            diffs.append(np.abs(bottom - top))

    if w // 8 >= 2:
        grid_x = np.diff(gray_f[:, ::8], axis=1)
        if grid_x.size:
            diffs.append(np.abs(grid_x))
    if h // 8 >= 2:
        grid_y = np.diff(gray_f[::8, :], axis=0)
        if grid_y.size:
            diffs.append(np.abs(grid_y))

    if not diffs:
        return 0.0
    stacked = np.concatenate([d.reshape(-1) for d in diffs])
    return float(np.mean(stacked))


def _wavelet_variance(gray: np.ndarray) -> Optional[float]:
    if pywt is None:
        return None
    coeffs = pywt.dwt2(gray.astype(np.float32), "db1")
    _, (cH, cV, cD) = coeffs
    detail = np.concatenate([cH.ravel(), cV.ravel(), cD.ravel()])
    if detail.size == 0:
        return 0.0
    return float(np.var(detail))


def noise_scores_from_gray(gray: np.ndarray) -> NoiseScores:
    """Compute noise metrics from a preprocessed grayscale image."""
    var_flat = _flat_variance(gray)
    jpeg_block = _jpeg_blockiness(gray)
    wavelet_var = _wavelet_variance(gray)
    return {
        "var_flat": var_flat,
        "wavelet_var": wavelet_var,
        "jpeg_block": jpeg_block,
    }


def noise_scores(img_bgr: np.ndarray) -> NoiseScores:
    """Return noise metrics for *img_bgr*.

    Parameters
    ----------
    img_bgr:
        Image array in BGR colour space.

    Returns
    -------
    dict
        Mapping containing ``var_flat``, ``wavelet_var`` and ``jpeg_block``.
    """

    gray = preprocess_gray(img_bgr)
    return noise_scores_from_gray(gray)


def is_noisy(scores: NoiseScores, thresholds: Dict[str, Optional[float]], method: str = "var_flat") -> bool:
    """Decide if an image is noisy based on metric thresholds."""
    method = method.lower()
    valid_methods = {"var_flat", "wavelet_var", "jpeg_block", "flat+block"}
    if method not in valid_methods:
        raise ValueError(f"Unknown noise method: {method}")

    def above(name: str) -> bool:
        value = scores.get(name)
        thr = thresholds.get(name)
        if value is None or thr is None:
            return False
        return value > thr

    if method == "var_flat":
        return above("var_flat")
    if method == "wavelet_var":
        return above("wavelet_var")
    if method == "jpeg_block":
        return above("jpeg_block")
    # flat+block
    return above("var_flat") or above("jpeg_block")
