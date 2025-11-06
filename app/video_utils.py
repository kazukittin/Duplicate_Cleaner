
import os
import cv2
import numpy as np
from PIL import Image
import imagehash
import hashlib

VIDEO_EXTS = {'.mp4', '.mov', '.avi', '.mkv', '.m4v', '.wmv'}

def is_video_path(path: str) -> bool:
    return os.path.splitext(path)[1].lower() in VIDEO_EXTS

def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1024*1024), b''):
            h.update(chunk)
    return h.hexdigest()

def first_frame_bgr(path: str):
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        return None
    ok, frame = cap.read()
    cap.release()
    if not ok or frame is None:
        return None
    return frame

def video_meta(path: str):
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        return None
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
    frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    cap.release()
    dur = frames / fps if fps > 0 else 0.0
    size = os.stat(path).st_size
    return {"w": w, "h": h, "fps": fps, "frames": frames, "duration": dur, "size": size}

def frame_iter(path: str, max_frames=12):
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        return
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    if total <= 0:
        count = 0
        while count < max_frames:
            ok, frame = cap.read()
            if not ok or frame is None:
                break
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            yield Image.fromarray(rgb)
            count += 1
        cap.release()
        return
    import numpy as _np
    idxs = _np.linspace(0, max(0, total-1), num=max_frames, dtype=int)
    for idx in idxs:
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(idx))
        ok, frame = cap.read()
        if not ok or frame is None:
            continue
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        yield Image.fromarray(rgb)
    cap.release()

def video_phash_hex(path: str, samples=12):
    hashes = []
    for im in frame_iter(path, max_frames=samples):
        try:
            h = imagehash.phash(im)
            hashes.append(int(str(h), 16))
        except Exception:
            continue
    if not hashes:
        return ""
    import numpy as _np
    med = int(_np.median(hashes))
    return f"{med:016x}"
