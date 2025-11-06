from PySide6.QtGui import QPixmap
from PIL import Image
import os
import tempfile

class ThumbnailProvider:
    def __init__(self):
        self.cache_dir = os.path.join(tempfile.gettempdir(), "dupsnap_thumb")
        os.makedirs(self.cache_dir, exist_ok=True)

    def thumb_path(self, src: str) -> str:
        base = src.replace(':','_').replace('/','_').replace('\\','_')
        return os.path.join(self.cache_dir, base + ".jpg")

    def get_pixmap(self, src: str, max_w=700, max_h=700):
        tp = self.thumb_path(src)
        if not os.path.exists(tp):
            try:
                with Image.open(src) as im:
                    im.thumbnail((max_w, max_h))
                    im.convert('RGB').save(tp, quality=85)
            except Exception:
                return None
        pix = QPixmap(tp)
        if pix.isNull():
            return None
        return pix
