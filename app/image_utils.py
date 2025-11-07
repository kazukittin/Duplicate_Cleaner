from PIL import Image
import imagehash
import cv2
import numpy as np
import hashlib
import os

IMG_EXTS = {'.jpg','.jpeg','.png','.bmp','.tiff','.webp'}

def is_image_path(path: str) -> bool:
    ext = os.path.splitext(path)[1].lower()
    return ext in IMG_EXTS

def get_image_meta(path: str):
    try:
        st = os.stat(path)
        with Image.open(path) as im:
            w, h = im.size
        return {"size": st.st_size, "w": w, "h": h}
    except Exception:
        return None

def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1024*1024), b''):
            h.update(chunk)
    return h.hexdigest()

def phash_hex(path: str) -> str:
    try:
        with Image.open(path) as im:
            return imagehash.phash(im).__str__()
    except Exception:
        return ''

def laplacian_variance(path: str) -> float:
    try:
        # np.fromfile で日本語パス対応
        data = np.fromfile(path, dtype=np.uint8)
        im = cv2.imdecode(data, cv2.IMREAD_GRAYSCALE)
        if im is None:
            return 0.0
        return float(cv2.Laplacian(im, cv2.CV_64F).var())
    except Exception:
        return 0.0

def noise_metric(path: str) -> float:
    try:
        data = np.fromfile(path, dtype=np.uint8)
        im = cv2.imdecode(data, cv2.IMREAD_GRAYSCALE)
        if im is None:
            return 0.0
        lap = cv2.Laplacian(im, cv2.CV_64F)
        _, stddev = cv2.meanStdDev(lap)
        return float(stddev[0][0])
    except Exception:
        return 0.0

def format_bytes(n: int) -> str:
    for unit in ['B','KB','MB','GB','TB']:
        if n < 1024:
            return f"{n:.1f}{unit}" if unit != 'B' else f"{n}{unit}"
        n /= 1024
    return f"{n:.1f}PB"
