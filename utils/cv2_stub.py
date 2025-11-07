"""Fallback OpenCV-like API implemented with NumPy and Pillow."""
from __future__ import annotations

from io import BytesIO
from typing import Iterable, Optional, Tuple

import numpy as np
from PIL import Image

COLOR_BGR2GRAY = 6
IMREAD_COLOR = 1
IMREAD_GRAYSCALE = 0
IMWRITE_JPEG_QUALITY = 1
INTER_AREA = 3
INTER_LINEAR = 1
CV_32F = np.float32
CV_64F = np.float64


def cvtColor(image: np.ndarray, code: int) -> np.ndarray:
    if code != COLOR_BGR2GRAY:
        raise NotImplementedError("Only BGR2GRAY conversion is supported")
    if image.ndim == 2:
        return image.astype(np.uint8, copy=False)
    b = image[..., 0].astype(np.float32)
    g = image[..., 1].astype(np.float32)
    r = image[..., 2].astype(np.float32)
    gray = 0.114 * b + 0.587 * g + 0.299 * r
    return np.clip(gray, 0, 255).astype(np.uint8)


def _to_pil(image: np.ndarray) -> Image.Image:
    if image.ndim == 2:
        return Image.fromarray(image.astype(np.uint8), mode="L")
    if image.shape[2] == 3:
        return Image.fromarray(image[..., ::-1].astype(np.uint8), mode="RGB")
    raise ValueError("Unsupported image shape")


def _from_pil(image: Image.Image, color: bool) -> np.ndarray:
    if color:
        arr = np.array(image.convert("RGB"), dtype=np.uint8)
        return arr[..., ::-1].copy()
    return np.array(image.convert("L"), dtype=np.uint8)


def resize(image: np.ndarray, dsize: Tuple[int, int], interpolation: int | None = None) -> np.ndarray:
    pil = _to_pil(image)
    resample = Image.BILINEAR
    if interpolation == INTER_AREA:
        resample = Image.BOX
    resized = pil.resize(dsize, resample=resample)
    return _from_pil(resized, image.ndim == 3)


def convertScaleAbs(src: np.ndarray) -> np.ndarray:
    return np.clip(np.abs(src), 0, 255).astype(np.uint8)


def _pad(image: np.ndarray, pad: int) -> np.ndarray:
    if image.ndim == 2:
        return np.pad(image, pad, mode="edge")
    return np.pad(image, ((pad, pad), (pad, pad), (0, 0)), mode="edge")


def _convolve2d(image: np.ndarray, kernel: np.ndarray) -> np.ndarray:
    pad = kernel.shape[0] // 2
    padded = _pad(image, pad)
    if image.ndim == 2:
        result = np.zeros_like(image, dtype=np.float32)
        for i in range(image.shape[0]):
            for j in range(image.shape[1]):
                region = padded[i : i + kernel.shape[0], j : j + kernel.shape[1]]
                result[i, j] = float(np.sum(region * kernel))
        return result
    else:
        result = np.zeros_like(image, dtype=np.float32)
        for c in range(image.shape[2]):
            result[..., c] = _convolve2d(image[..., c], kernel)
        return result


def GaussianBlur(image: np.ndarray, ksize: Tuple[int, int], sigma: float) -> np.ndarray:
    kx, ky = ksize
    if kx != ky or kx % 2 == 0:
        raise ValueError("GaussianBlur requires odd square kernel")
    ax = np.arange(-(kx // 2), kx // 2 + 1, dtype=np.float32)
    kernel = np.exp(-(ax ** 2) / (2 * sigma * sigma))
    kernel = np.outer(kernel, kernel)
    kernel /= kernel.sum()
    blurred = _convolve2d(image, kernel)
    return np.clip(blurred, 0, 255).astype(np.uint8)


_SOBEL_X = np.array([[1, 0, -1], [2, 0, -2], [1, 0, -1]], dtype=np.float32)
_SOBEL_Y = np.array([[1, 2, 1], [0, 0, 0], [-1, -2, -1]], dtype=np.float32)
_LAPLACIAN = np.array([[0, 1, 0], [1, -4, 1], [0, 1, 0]], dtype=np.float32)


def Sobel(image: np.ndarray, ddepth: float, dx: int, dy: int, ksize: int = 3) -> np.ndarray:
    if ksize != 3:
        raise NotImplementedError("Only 3x3 Sobel is supported")
    if dx == 1 and dy == 0:
        kernel = _SOBEL_X
    elif dx == 0 and dy == 1:
        kernel = _SOBEL_Y
    else:
        raise NotImplementedError("Unsupported Sobel direction")
    return _convolve2d(image.astype(np.float32), kernel)


def magnitude(x: np.ndarray, y: np.ndarray) -> np.ndarray:
    return np.sqrt(x * x + y * y)


def Laplacian(image: np.ndarray, ddepth: float, ksize: int = 3) -> np.ndarray:
    if ksize != 3:
        raise NotImplementedError("Only 3x3 Laplacian is supported")
    return _convolve2d(image.astype(np.float32), _LAPLACIAN)


def imdecode(buf: np.ndarray, flags: int = IMREAD_COLOR) -> Optional[np.ndarray]:
    if isinstance(buf, np.ndarray):
        data = buf.tobytes()
    else:
        data = bytes(buf)
    try:
        image = Image.open(BytesIO(data))
    except Exception:
        return None
    color = flags != IMREAD_GRAYSCALE
    return _from_pil(image, color)


def imencode(ext: str, image: np.ndarray, params: Optional[Iterable[int]] = None) -> Tuple[bool, np.ndarray]:
    pil = _to_pil(image)
    buffer = BytesIO()
    save_kwargs = {}
    if params:
        params = list(params)
        for i in range(0, len(params), 2):
            if params[i] == IMWRITE_JPEG_QUALITY:
                save_kwargs["quality"] = int(params[i + 1])
    format_name = ext.lstrip(".").upper()
    if format_name == "JPG":
        format_name = "JPEG"
    if format_name == "TIF":
        format_name = "TIFF"
    pil.save(buffer, format=format_name, **save_kwargs)
    data = np.frombuffer(buffer.getvalue(), dtype=np.uint8)
    return True, data


def imwrite(path: str, image: np.ndarray) -> bool:
    try:
        pil = _to_pil(image)
        pil.save(path)
        return True
    except Exception:
        return False
