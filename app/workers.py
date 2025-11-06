from PySide6.QtCore import QThread, Signal
import os
from .image_utils import is_image_path, get_image_meta, sha256_file, phash_hex, laplacian_variance
from .models import ResultGroup, ResultItem

class ScanWorker(QThread):
    sig_progress = Signal(int)
    sig_finished = Signal(list)  # list[ResultGroup]
    sig_error = Signal(str)

    def __init__(self, folder: str, sim_thresh: int = 5):
        super().__init__()
        self.folder = folder
        self.sim_thresh = sim_thresh  # Hamming distance threshold

    def run(self):
        try:
            files = []
            for root, _, fns in os.walk(self.folder):
                for fn in fns:
                    p = os.path.join(root, fn)
                    if is_image_path(p):
                        files.append(p)
            total = len(files)
            if total == 0:
                self.sig_finished.emit([])
                return

            items = []
            hashes = {}
            for i, p in enumerate(files, start=1):
                meta = get_image_meta(p)
                if not meta:
                    continue
                h = sha256_file(p)
                it = ResultItem(path=p, size=meta['size'], width=meta['w'], height=meta['h'])
                it.sha256 = h
                items.append(it)
                hashes.setdefault(h, []).append(it)
                if i % 20 == 0:
                    self.sig_progress.emit(int(i/total*30))

            groups: list[ResultGroup] = []
            for h, arr in hashes.items():
                if len(arr) > 1:
                    g = ResultGroup(kind="重複", title=f"SHA256 {h[:8]}...", items=arr, score=None)
                    groups.append(g)

            # Auto-select lower-res in duplicate groups (keep the largest resolution)
            for g in groups:
                if g.items:
                    keep = max(g.items, key=lambda it: (it.pixels, it.size))
                    for it in g.items:
                        it.similarity = 1.0 if it is not keep else None  # mark others as delete candidates

            unique_items = [it for it in items if not any(it in g.items for g in groups)]
            for i, it in enumerate(unique_items, start=1):
                it.phash = phash_hex(it.path)  # 16進64bit
                if i % 20 == 0:
                    self.sig_progress.emit(30 + int(i/len(unique_items)*40))

            MAX_SIM = 2000
            sim_groups = []
            if len(unique_items) <= MAX_SIM:
                visited = set()
                for i, a in enumerate(unique_items):
                    if i in visited:
                        continue
                    grp = [a]
                    for j in range(i+1, len(unique_items)):
                        b = unique_items[j]
                        if hamming(a.phash, b.phash) <= self.sim_thresh:
                            grp.append(b)
                            visited.add(j)
                    if len(grp) >= 2:
                        g = ResultGroup(kind="類似", title=f"pHash group {a.phash[:8]}", items=grp, score=1.0)
                        # Auto-select lower-res (keep biggest)
                        keep = max(grp, key=lambda it: (it.pixels, it.size))
                        for it in grp:
                            it.similarity = 1.0 if it is not keep else None
                        sim_groups.append(g)
            groups.extend(sim_groups)

            for k, g in enumerate(groups, start=1):
                for it in g.items:
                    it.blur = laplacian_variance(it.path)
                self.sig_progress.emit(70 + int(k/len(groups)*25))

            self.sig_progress.emit(100)
            self.sig_finished.emit(groups)
        except Exception as e:
            self.sig_error.emit(str(e))

HEX_TO_BITS = {f"{i:x}": format(i, '04b') for i in range(16)}

def hamming(h1: str, h2: str) -> int:
    if not h1 or not h2:
        return 64
    b1 = ''.join(HEX_TO_BITS.get(c, "0000") for c in h1.lower())
    b2 = ''.join(HEX_TO_BITS.get(c, "0000") for c in h2.lower())
    return sum(ch1 != ch2 for ch1, ch2 in zip(b1, b2))
