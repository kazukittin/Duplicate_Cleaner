"""Blur detection utilities."""

from __future__ import annotations

from typing import Dict

import cv2
import numpy as np

__all__ = ["blur_scores", "is_blurry", "intensity_variance"]

_LONG_SIDE = 1024
_LOW_TEXTURE_EPSILON = 1.0


def _resize_long_side(img: np.ndarray, target: int = _LONG_SIDE) -> np.ndarray:
    """Resize image so that its long side equals ``target`` pixels."""
    if img is None or img.size == 0:
        raise ValueError("Empty image provided to blur scoring")
    h, w = img.shape[:2]
    if h == 0 or w == 0:
        raise ValueError("Image with zero dimension provided to blur scoring")
    max_dim = max(h, w)
    if max_dim <= target:
        return img
    scale = target / float(max_dim)
    new_w = max(1, int(round(w * scale)))
    new_h = max(1, int(round(h * scale)))
    return cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)


def _to_gray(image: np.ndarray) -> np.ndarray:
    """Return a normalized grayscale version of the image as ``float32``."""
    if image.ndim == 2:
        gray = image
    elif image.ndim == 3:
        channels = image.shape[2]
        if channels == 1:
            gray = image[:, :, 0]
        elif channels == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            gray = cv2.cvtColor(image, cv2.COLOR_BGRA2GRAY)
    else:
        raise ValueError("Unsupported image shape for blur scoring")
    if gray.dtype != np.float32:
        gray = gray.astype(np.float32)
    return gray


def _prepare_gray(image: np.ndarray) -> np.ndarray:
    resized = _resize_long_side(image)
    return _to_gray(resized)


def _high_frequency_ratio(gray: np.ndarray) -> float:
    """Compute the ratio of high-frequency energy in the image."""
    if gray.size == 0:
        return 0.0
    fft = np.fft.fft2(gray)
    fft_shifted = np.fft.fftshift(fft)
    magnitude_sq = np.abs(fft_shifted) ** 2
    h, w = gray.shape
    radius = max(1, int(round(0.05 * min(h, w))))
    cy, cx = h // 2, w // 2
    y, x = np.ogrid[:h, :w]
    mask = (y - cy) ** 2 + (x - cx) ** 2 > radius ** 2
    total_energy = float(magnitude_sq.sum())
    if total_energy <= 0.0:
        return 0.0
    high_freq_energy = float(magnitude_sq[mask].sum())
    return high_freq_energy / total_energy


def blur_scores(img_bgr: np.ndarray) -> Dict[str, float]:
    """Return blur related metrics for the provided image.

    Parameters
    ----------
    img_bgr:
        Image array in BGR (OpenCV) channel order.

    Returns
    -------
    dict
        Mapping of metric names to values.
    """
    gray = _prepare_gray(img_bgr)
    lap = cv2.Laplacian(gray, cv2.CV_32F)
    vol = float(lap.var())
    gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    tenengrad = float(np.mean(gx ** 2 + gy ** 2))
    hfr = _high_frequency_ratio(gray)
    return {"vol": vol, "tenengrad": tenengrad, "hfr": hfr}


def intensity_variance(img_bgr: np.ndarray) -> float:
    """Compute the global intensity variance for blur guard heuristics."""
    gray = _prepare_gray(img_bgr)
    return float(np.var(gray))


def is_blurry(scores: Dict[str, float], thr: Dict[str, float], *, method: str = "vol+hfr") -> bool:
    """Return whether the image is classified as blurry.

    Parameters
    ----------
    scores:
        Metrics produced by :func:`blur_scores`.
    thr:
        Thresholds for metrics.
    method:
        Classification strategy: ``"vol"``, ``"hfr"``, or ``"vol+hfr"``.
    """
    method = (method or "").lower()
    if method not in {"vol", "hfr", "vol+hfr"}:
        raise ValueError(f"Unknown blur method: {method}")

    if method == "vol":
        return scores.get("vol", float("inf")) < thr.get("vol", 0.0)
    if method == "hfr":
        return scores.get("hfr", float("inf")) < thr.get("hfr", 0.0)
    return (
        scores.get("vol", float("inf")) < thr.get("vol", 0.0)
        and scores.get("hfr", float("inf")) < thr.get("hfr", 0.0)
    )


def low_texture_epsilon() -> float:
    """Return the epsilon used to detect low-texture datasets."""
    return _LOW_TEXTURE_EPSILON
