
from PySide6.QtCore import QThread, Signal
import os
from .image_utils import is_image_path, get_image_meta, sha256_file as img_sha256, phash_hex, laplacian_variance
from .video_utils import is_video_path, video_meta, sha256_file as vid_sha256, video_phash_hex
from .models import ResultGroup, ResultItem
from .cache_db import HashCache

class ScanWorker(QThread):
    sig_progress = Signal(int)
    sig_finished = Signal(list)
    sig_error = Signal(str)

    def __init__(self, folder: str, sim_thresh: int = 5, db_path: str = None):
        super().__init__()
        self.folder = folder
        self.sim_thresh = sim_thresh
        self.db_path = db_path or os.path.join(os.getcwd(), "dupsnap_cache.db")

    def run(self):
        cache = None
        try:
            cache = HashCache(self.db_path)
            files = []
            for root, _, fns in os.walk(self.folder):
                for fn in fns:
                    p = os.path.join(root, fn)
                    if is_image_path(p) or is_video_path(p):
                        try:
                            st = os.stat(p)
                            files.append((p, st.st_size, st.st_mtime))
                        except Exception:
                            continue

            total = len(files)
            if total == 0:
                self.sig_finished.emit([])
                return

            items = []
            dup_groups_map = {}

            for i, (p, size, mtime) in enumerate(files, start=1):
                kind = "img" if is_image_path(p) else ("vid" if is_video_path(p) else "other")
                row = cache.get(p, size, mtime)
                if row:
                    sha256, ph, w, h, kind_cached = row
                    kind = kind_cached or kind
                    if w is None or h is None:
                        if kind == "img":
                            meta = get_image_meta(p) or {"w":0,"h":0,"size":size}
                        else:
                            meta = video_meta(p) or {"w":0,"h":0,"size":size}
                        w, h = meta.get("w",0), meta.get("h",0)
                        cache.upsert(p, size, mtime, sha256 or "", ph or "", w, h, kind)
                else:
                    if kind == "img":
                        meta = get_image_meta(p)
                        if not meta: continue
                        w, h = meta["w"], meta["h"]
                        sha256 = img_sha256(p)
                        ph = ""
                    else:
                        meta = video_meta(p)
                        if not meta: continue
                        w, h = meta["w"], meta["h"]
                        sha256 = vid_sha256(p)
                        ph = ""
                    cache.upsert(p, size, mtime, sha256, ph, w, h, kind)

                it = ResultItem(path=p, size=size, width=w or 0, height=h or 0)
                it.sha256 = sha256 or ""
                items.append(it)
                dup_groups_map.setdefault(it.sha256, []).append(it)

                if i % 50 == 0:
                    cache.commit()
                    self.sig_progress.emit(int(i/total*20))

            groups = []
            for h, arr in dup_groups_map.items():
                if h and len(arr) > 1:
                    g = ResultGroup(kind="重複", title=f"SHA256 {h[:8]}...", items=arr, score=None)
                    keep = max(arr, key=lambda it: (it.width*it.height, it.size))
                    for it in arr:
                        it.similarity = 1.0 if it is not keep else None
                    groups.append(g)

            unique_items = [it for it in items if not any(it in g.items for g in groups)]
            total2 = max(1, len(unique_items))
            for i, it in enumerate(unique_items, start=1):
                try:
                    st = os.stat(it.path)
                    row = cache.get(it.path, st.st_size, st.st_mtime)
                except Exception:
                    row = None
                ph = None
                if row and row[1]:
                    ph = row[1]
                else:
                    if is_image_path(it.path):
                        ph = phash_hex(it.path)
                    else:
                        ph = video_phash_hex(it.path, samples=12)
                    cache.upsert(it.path, st.st_size, st.st_mtime, it.sha256, ph or "", it.width, it.height, "img" if is_image_path(it.path) else "vid")
                it.phash = ph or ""
                if i % 50 == 0:
                    cache.commit()
                    self.sig_progress.emit(20 + int(i/total2*35))

            from collections import defaultdict
            buckets = defaultdict(list)
            for it in unique_items:
                if it.phash:
                    buckets[it.phash[:4]].append(it)

            processed = 0
            total_b = max(1, len(buckets))
            for prefix, arr in buckets.items():
                if len(arr) < 2:
                    processed += 1
                    continue
                visited = set()
                for i, a in enumerate(arr):
                    if i in visited or not a.phash:
                        continue
                    grp = [a]
                    for j in range(i+1, len(arr)):
                        b = arr[j]
                        if not b.phash:
                            continue
                        if hamming(a.phash, b.phash) <= self.sim_thresh:
                            grp.append(b); visited.add(j)
                    if len(grp) >= 2:
                        keep = max(grp, key=lambda it: (it.width*it.height, it.size))
                        for it2 in grp:
                            it2.similarity = 1.0 if it2 is not keep else None
                        groups.append(ResultGroup(kind="類似", title=f"pHash {prefix}", items=grp, score=1.0))
                processed += 1
                if processed % 20 == 0:
                    self.sig_progress.emit(55 + int(processed/total_b*35))

            for k, g in enumerate(groups, start=1):
                for it in g.items:
                    if is_image_path(it.path):
                        it.blur = laplacian_variance(it.path)
                    else:
                        it.blur = None
                if k % 20 == 0:
                    self.sig_progress.emit(95)

            cache.commit()
            self.sig_progress.emit(100)
            self.sig_finished.emit(groups)
        except Exception as e:
            self.sig_error.emit(str(e))
        finally:
            if cache:
                cache.close()

HEX_TO_BITS = {f"{i:x}": format(i, '04b') for i in range(16)}

def hamming(h1: str, h2: str) -> int:
    if not h1 or not h2:
        return 64
    b1 = ''.join(HEX_TO_BITS.get(c, "0000") for c in h1.lower())
    b2 = ''.join(HEX_TO_BITS.get(c, "0000") for c in h2.lower())
    return sum(ch1 != ch2 for ch1, ch2 in zip(b1, b2))
