
from PySide6.QtCore import QThread, Signal
import os
import time
import math
from .image_utils import (
    is_image_path,
    get_image_meta,
    sha256_file as img_sha256,
    phash_hex,
    noise_metric,
)
from .video_utils import is_video_path, video_meta, sha256_file as vid_sha256, video_phash_hex
from .models import ResultGroup, ResultItem
from .cache_db import HashCache


def similarity_score_from_distance(dist: int | None) -> int | None:
    if dist is None:
        return None
    score = 100.0 - (dist / 64.0) * 100.0
    return int(max(1, min(100, round(score))))


def noise_score_from_value(noise_value: float | None, threshold: float | None) -> int | None:
    if noise_value is None or not threshold or threshold <= 0:
        return None
    severity = (noise_value - threshold) / threshold
    if severity < 0:
        return None
    if severity == 0:
        score = 1.0
    else:
        score = severity * 100.0
    return int(max(1, min(100, round(score))))

class ScanWorker(QThread):
    sig_progress = Signal(int)
    sig_finished = Signal(list)
    sig_error = Signal(str)
    sig_stage = Signal(str)

    SIMILARITY_LEVELS = {
        "weak": 3,
        "medium": 5,
        "strong": 8,
    }
    NOISE_LEVELS = {
        "weak": 0.1,
        "medium": 0.3,
        "strong": 0.6,
    }

    def __init__(
        self,
        folder: str,
        sim_level: str = "medium",
        noise_level: str = "medium",
        db_path: str = None,
        sim_thresh: int | None = None,
    ):
        super().__init__()
        self.folder = folder
        if sim_thresh is not None:
            try:
                self.sim_threshold = max(0, min(64, int(sim_thresh)))
            except (TypeError, ValueError):
                self.sim_threshold = self.SIMILARITY_LEVELS.get("medium", 5)
            self.sim_level = None
        else:
            level = sim_level if sim_level in self.SIMILARITY_LEVELS else "medium"
            self.sim_level = level
            self.sim_threshold = self.SIMILARITY_LEVELS.get(level, 5)
        self.noise_level = noise_level if noise_level in self.NOISE_LEVELS else "medium"
        self.db_path = db_path or os.path.join(os.getcwd(), "dupsnap_cache.db")

    def run(self):
        cache = None
        last_stage_text = None
        last_stage_time = 0.0
        last_stage_prefix = None

        def emit_stage(text: str, force: bool = False):
            nonlocal last_stage_text, last_stage_time, last_stage_prefix
            now = time.monotonic()
            prefix = text.split("(", 1)[0].strip()
            if force or last_stage_text is None or prefix != last_stage_prefix:
                self.sig_stage.emit(text)
                last_stage_text = text
                last_stage_time = now
                last_stage_prefix = prefix
                return
            if text == last_stage_text and now - last_stage_time < 1.0:
                return
            if now - last_stage_time < 0.1:
                return
            self.sig_stage.emit(text)
            last_stage_text = text
            last_stage_time = now
            last_stage_prefix = prefix

        try:
            cache = HashCache(self.db_path)
            files = []
            emit_stage("ファイル収集中…", force=True)
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
                emit_stage("対象ファイルなし (0/0)", force=True)
                self.sig_finished.emit([])
                return

            items = []
            dup_groups_map = {}

            for i, (p, size, mtime) in enumerate(files, start=1):
                emit_stage(f"メタデータ取得中 ({i}/{total})")
                kind = "img" if is_image_path(p) else ("vid" if is_video_path(p) else "other")
                row = cache.get(p, size, mtime)
                if row:
                    sha256, ph, w, h, kind_cached, noise_cached = row
                    kind = kind_cached or kind
                    if w is None or h is None:
                        if kind == "img":
                            meta = get_image_meta(p) or {"w":0,"h":0,"size":size}
                        else:
                            meta = video_meta(p) or {"w":0,"h":0,"size":size}
                        w, h = meta.get("w",0), meta.get("h",0)
                        cache.upsert(p, size, mtime, sha256 or "", ph or "", w, h, kind, noise_cached)
                    noise_val = noise_cached
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
                    cache.upsert(p, size, mtime, sha256, ph, w, h, kind, None)
                    noise_val = None

                it = ResultItem(path=p, size=size, width=w or 0, height=h or 0, mtime=mtime, noise=noise_val)
                it.sha256 = sha256 or ""
                items.append(it)
                dup_groups_map.setdefault(it.sha256, []).append(it)

                if i % 50 == 0:
                    cache.commit()
                    self.sig_progress.emit(int(i/total*20))

            groups = []
            for h, arr in dup_groups_map.items():
                if h and len(arr) > 1:
                    g = ResultGroup(kind="重複", title=f"SHA256 {h[:8]}...", items=arr, score=100)
                    keep = max(arr, key=lambda it: (it.width*it.height, it.size))
                    for it in arr:
                        it.similarity = 100 if it is not keep else None
                    groups.append(g)

            unique_items = [it for it in items if not any(it in g.items for g in groups)]
            unique_total = len(unique_items)
            if not unique_total:
                emit_stage("類似判定準備中 (0/0)", force=True)
            total2 = max(1, unique_total)
            for i, it in enumerate(unique_items, start=1):
                emit_stage(f"類似判定準備中 ({i}/{unique_total})" if unique_total else "類似判定準備中 (0/0)")
                size_key = it.size
                mtime_key = it.mtime
                try:
                    st = os.stat(it.path)
                    size_key = st.st_size
                    mtime_key = st.st_mtime
                except Exception:
                    st = None

                row = None
                if size_key is not None and mtime_key is not None:
                    try:
                        row = cache.get(it.path, size_key, mtime_key)
                    except Exception:
                        row = None

                ph = None
                noise_cached = None
                kind_cached = None
                if row:
                    noise_cached = row[5]
                    kind_cached = row[4]
                    if row[1]:
                        ph = row[1]

                if not ph:
                    is_img = is_image_path(it.path)
                    kind_for_cache = kind_cached or ("img" if is_img else "vid")
                    if is_img:
                        ph = phash_hex(it.path)
                    else:
                        ph = video_phash_hex(it.path, samples=12)
                    if size_key is not None and mtime_key is not None:
                        cache.upsert(
                            it.path,
                            size_key,
                            mtime_key,
                            it.sha256 or "",
                            ph or "",
                            it.width,
                            it.height,
                            kind_for_cache,
                            it.noise,
                        )
                it.phash = ph or ""
                if it.noise is None and noise_cached is not None:
                    it.noise = noise_cached
                if size_key is not None:
                    it.size = size_key
                if mtime_key is not None:
                    it.mtime = mtime_key
                if i % 50 == 0:
                    cache.commit()
                    self.sig_progress.emit(20 + int(i/total2*35))

            from collections import defaultdict
            buckets = defaultdict(list)
            for it in unique_items:
                if it.phash:
                    buckets[it.phash[:4]].append(it)

            processed = 0
            bucket_total = len(buckets)
            if not bucket_total:
                emit_stage("類似グループ化 (0/0)", force=True)
            total_b = max(1, bucket_total)
            for prefix, arr in buckets.items():
                if len(arr) < 2:
                    processed += 1
                    if bucket_total:
                        emit_stage(f"類似グループ化 ({processed}/{bucket_total})")
                    continue
                visited = set()
                for i, a in enumerate(arr):
                    if i in visited or not a.phash:
                        continue
                    members: list[ResultItem] = [a]
                    for j in range(i+1, len(arr)):
                        b = arr[j]
                        if not b.phash:
                            continue
                        dist = hamming(a.phash, b.phash)
                        if dist <= self.sim_threshold:
                            members.append(b)
                            visited.add(j)
                    if len(members) >= 2:
                        grp_items = list(members)
                        keep = max(grp_items, key=lambda it: (it.width*it.height, it.size))
                        group_score = None
                        for item in members:
                            if item is keep:
                                item.similarity = None
                                continue
                            dist = hamming(keep.phash, item.phash) if keep.phash and item.phash else None
                            score = similarity_score_from_distance(dist)
                            item.similarity = score
                            if score is not None:
                                group_score = score if group_score is None else max(group_score, score)
                        if group_score is None:
                            group_score = 100
                        groups.append(ResultGroup(kind="類似", title=f"pHash {prefix}", items=grp_items, score=group_score))
                    visited.add(i)
                processed += 1
                if bucket_total:
                    emit_stage(f"類似グループ化 ({processed}/{bucket_total})")
                if processed % 20 == 0:
                    self.sig_progress.emit(55 + int(processed/total_b*35))

            img_items = [it for it in items if is_image_path(it.path)]
            noise_total = len(img_items)
            if not noise_total:
                emit_stage("ノイズ判定 (0/0)", force=True)
            total_noise = max(1, noise_total)
            last_progress = 90
            noise_values: list[float] = []
            for idx, it in enumerate(img_items, start=1):
                emit_stage(f"ノイズ判定 ({idx}/{noise_total})" if noise_total else "ノイズ判定 (0/0)")
                if it.noise is None:
                    it.noise = noise_metric(it.path)
                    try:
                        st = os.stat(it.path)
                        cache.upsert(it.path, st.st_size, st.st_mtime, it.sha256 or "", it.phash or "",
                                     it.width, it.height, "img", it.noise)
                    except Exception:
                        pass
                if it.noise is not None:
                    noise_values.append(it.noise)
                progress = 90 + int(idx / total_noise * 5)
                if progress > last_progress:
                    self.sig_progress.emit(progress)
                    last_progress = progress
            for it in items:
                if not is_image_path(it.path):
                    it.noise = None

            noise_candidates: list[ResultItem] = []
            dynamic_noise_threshold: float | None = None
            if noise_values:
                positive_vals = sorted(v for v in noise_values if v is not None and v > 0)
                if positive_vals:
                    frac = self.NOISE_LEVELS.get(self.noise_level, 0.3)
                    count = len(positive_vals)
                    take = max(1, math.ceil(count * frac))
                    idx = max(0, count - take)
                    dynamic_noise_threshold = positive_vals[idx]

            candidate_threshold: float | None = dynamic_noise_threshold

            if candidate_threshold and candidate_threshold > 0:
                for it in img_items:
                    if it.noise is None or it.noise < candidate_threshold:
                        continue
                    score = noise_score_from_value(it.noise, candidate_threshold)
                    if score is None:
                        continue
                    it.noise_score = score
                    noise_candidates.append(it)

            if noise_candidates:
                noise_candidates.sort(key=lambda it: it.noise_score if it.noise_score is not None else 0, reverse=True)
                max_score = max((it.noise_score for it in noise_candidates if it.noise_score is not None), default=None)
                if candidate_threshold:
                    title = f"ノイズ疑い (≳ {int(round(candidate_threshold))})"
                else:
                    title = "ノイズ疑い"
                groups.append(ResultGroup(kind="ノイズ", title=title, items=noise_candidates, score=max_score))

            cache.commit()
            self.sig_progress.emit(100)
            emit_stage("完了", force=True)
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
