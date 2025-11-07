"""Command line interface for DupSnap blur-aware processing."""

from __future__ import annotations

import argparse
import csv
import itertools
import logging
import os
import shutil
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

import cv2
import numpy as np

from app.image_utils import is_image_path
from utils.blur import (
    blur_scores,
    intensity_variance,
    is_blurry,
    low_texture_epsilon,
)


Decision = Tuple[str, str]  # (decision, reason)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Duplicate cleaner helper with blur detection")
    parser.add_argument("--input", required=True, help="Input directory containing images")
    parser.add_argument("--drop-blurry", action="store_true", help="Exclude blurry images from downstream steps")
    parser.add_argument(
        "--blur-percentile",
        type=int,
        default=20,
        help="Percentile (5-50) used to set blur thresholds",
    )
    parser.add_argument(
        "--blur-method",
        choices=["vol", "hfr", "vol+hfr"],
        default="vol+hfr",
        help="Blur detection method",
    )
    parser.add_argument(
        "--blur-list",
        help="Optional CSV file to store blur scores and decisions",
    )
    parser.add_argument(
        "--blur-move-dir",
        help="Directory to move blurry images into instead of keeping them in-place",
    )
    parser.add_argument(
        "--blur-sample-limit",
        type=int,
        default=5000,
        help="Maximum number of images to sample when estimating thresholds",
    )
    return parser.parse_args()


def gather_images(root: Path) -> List[Path]:
    if root.is_file():
        return [root] if is_image_path(str(root)) else []
    images: List[Path] = []
    for dirpath, _, filenames in os.walk(root):
        for fn in filenames:
            path = Path(dirpath) / fn
            if is_image_path(str(path)):
                images.append(path)
    images.sort()
    return images


def load_image(path: Path) -> np.ndarray | None:
    try:
        data = np.fromfile(str(path), dtype=np.uint8)
        if data.size == 0:
            return None
        image = cv2.imdecode(data, cv2.IMREAD_UNCHANGED)
        return image
    except Exception:
        return None


def compute_thresholds(
    paths: Iterable[Path], percentile: int, sample_limit: int
) -> Tuple[float, float, float, Dict[Path, Tuple[Dict[str, float], float]]]:
    vol_scores: List[float] = []
    hfr_scores: List[float] = []
    intensity_vars: List[float] = []
    cached: Dict[Path, Tuple[Dict[str, float], float]] = {}
    for path in itertools.islice(paths, sample_limit):
        image = load_image(path)
        if image is None:
            logging.warning("Failed to read image for sampling: %s", path)
            continue
        try:
            scores = blur_scores(image)
            var = intensity_variance(image)
        except Exception as exc:  # pragma: no cover - defensive
            logging.warning("Error computing blur scores for %s: %s", path, exc)
            continue
        vol_scores.append(scores["vol"])
        hfr_scores.append(scores["hfr"])
        intensity_vars.append(var)
        cached[path] = (scores, var)
    thr_vol = float(np.percentile(vol_scores, percentile)) if vol_scores else 0.0
    thr_hfr = float(np.percentile(hfr_scores, percentile)) if hfr_scores else 0.0
    global_intensity_var = float(np.median(intensity_vars)) if intensity_vars else 0.0
    return thr_vol, thr_hfr, global_intensity_var, cached


def unique_destination(src: Path, dest_dir: Path) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    candidate = dest_dir / src.name
    if not candidate.exists():
        return candidate
    stem = src.stem
    suffix = src.suffix
    for idx in itertools.count(1):
        candidate = dest_dir / f"{stem}_{idx}{suffix}"
        if not candidate.exists():
            return candidate
    raise RuntimeError("Failed to create unique destination path")


def decide_for_image(
    scores: Dict[str, float],
    method: str,
    skip_blur: bool,
    blur_flag: bool,
) -> Decision:
    if skip_blur:
        return ("low_texture", "dataset_low_texture")
    if blur_flag:
        return ("blurry", f"{method}")
    return ("keep", "ok")


def main() -> int:
    args = parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    if not 5 <= args.blur_percentile <= 50:
        raise SystemExit("--blur-percentile must be between 5 and 50")
    if args.blur_sample_limit <= 0:
        raise SystemExit("--blur-sample-limit must be a positive integer")

    input_path = Path(args.input).expanduser().resolve()
    if not input_path.exists():
        raise SystemExit(f"Input path does not exist: {input_path}")

    images = gather_images(input_path)
    if not images:
        logging.info("No image files found under %s", input_path)
        return 0

    logging.info("Collected %d images", len(images))

    thr_vol, thr_hfr, global_var, cached = compute_thresholds(images, args.blur_percentile, args.blur_sample_limit)
    skip_blur = global_var < low_texture_epsilon()
    if skip_blur:
        logging.info(
            "Global intensity variance %.4f below epsilon %.4f → marking as low_texture",
            global_var,
            low_texture_epsilon(),
        )
    else:
        logging.info(
            "Blur thresholds (P%d): vol=%.3f, hfr=%.5f (from %d samples)",
            args.blur_percentile,
            thr_vol,
            thr_hfr,
            len(cached),
        )

    writer = None
    csv_file = None
    if args.blur_list:
        csv_path = Path(args.blur_list)
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        csv_file = csv_path.open("w", newline="", encoding="utf-8")
        writer = csv.writer(csv_file)
        writer.writerow(["path", "vol", "tenengrad", "hfr", "decision", "reason"])

    thr_map = {"vol": thr_vol, "hfr": thr_hfr}
    counts = {"blurry": 0, "keep": 0, "low_texture": 0, "error": 0}
    moved = 0

    try:
        for path in images:
            image = load_image(path)
            if image is None:
                counts["error"] += 1
                if writer:
                    writer.writerow([str(path), "", "", "", "error", "unreadable_image"])
                logging.warning("Failed to read image: %s", path)
                continue
            if path in cached:
                scores, _ = cached[path]
            else:
                try:
                    scores = blur_scores(image)
                except Exception as exc:  # pragma: no cover - defensive
                    counts["error"] += 1
                    if writer:
                        writer.writerow([str(path), "", "", "", "error", f"metric_error:{exc}"])
                    logging.warning("Error computing blur scores for %s: %s", path, exc)
                    continue
            blur_flag = False
            if not skip_blur:
                blur_flag = is_blurry(scores, thr_map, method=args.blur_method)
            decision, reason = decide_for_image(scores, args.blur_method, skip_blur, blur_flag)
            counts[decision] += 1

            if decision == "blurry" and args.blur_move_dir:
                dest = unique_destination(path, Path(args.blur_move_dir))
                shutil.move(str(path), dest)
                moved += 1
                reason = f"{reason};moved"
            if writer:
                writer.writerow([
                    str(path),
                    f"{scores['vol']:.6f}",
                    f"{scores['tenengrad']:.6f}",
                    f"{scores['hfr']:.6f}",
                    decision,
                    reason,
                ])
    finally:
        if csv_file:
            csv_file.close()

    logging.info(
        "Blur decisions: keep=%d, blurry=%d, low_texture=%d, error=%d", counts["keep"], counts["blurry"], counts["low_texture"], counts["error"]
    )
    if args.blur_move_dir:
        logging.info("Moved %d blurry images to %s", moved, args.blur_move_dir)
    if args.drop_blurry:
        logging.info("--drop-blurry specified: blurry images excluded from downstream processing")
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
