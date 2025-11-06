
from PySide6.QtGui import QPixmap, QImage
from PIL import Image
import os
import tempfile
from .video_utils import is_video_path, first_frame_bgr

class ThumbnailProvider:
    def __init__(self):
        self.cache_dir = os.path.join(tempfile.gettempdir(), "dupsnap_thumb")
        os.makedirs(self.cache_dir, exist_ok=True)

    def thumb_path(self, src: str, max_w: int, max_h: int) -> str:
        base = src.replace(':','_').replace('/','_').replace('\\','_')
        return os.path.join(self.cache_dir, f"{base}_{max_w}x{max_h}.jpg")

    def get_pixmap(self, src: str, max_w=700, max_h=700):
        tp = self.thumb_path(src, max_w, max_h)
        if not os.path.exists(tp):
            try:
                if is_video_path(src):
                    import cv2
                    frame = first_frame_bgr(src)
                    if frame is None:
                        return None
                    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    im = Image.fromarray(rgb)
                else:
                    im = Image.open(src)
                im.thumbnail((max_w, max_h))
                im = im.convert('RGB')
                im.save(tp, quality=85)
            except Exception:
                return None
        pix = QPixmap(tp)
        if pix.isNull():
            return None
        return pix
