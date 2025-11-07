from __future__ import annotations

import argparse
import csv
import logging
import os
import random
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np

from utils.blur import compute_blur_with_gray
from utils.noise import is_noisy, noise_scores_from_gray

try:
    import cv2  # type: ignore
except ImportError:  # pragma: no cover - fallback when OpenCV is unavailable
    from utils import cv2_stub as cv2  # type: ignore

IMG_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif", ".webp"}


@dataclass
class ImageMetrics:
    path: Path
    blur_score: float
    noise_scores: Dict[str, Optional[float]]
    decision: str
    reason: str


@dataclass
class Thresholds:
    blur: float
    noise: Dict[str, Optional[float]]


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Duplicate Cleaner CLI")
    parser.add_argument("--input", required=True, help="Input directory with images")
    parser.add_argument(
        "--drop-blurry",
        action="store_true",
        help="Exclude images detected as blurry",
    )
    parser.add_argument(
        "--blur-percentile",
        type=float,
        default=20.0,
        help="Percentile threshold for blur detection (lower keeps more images)",
    )
    parser.add_argument(
        "--drop-noisy",
        action="store_true",
        help="Exclude noisy images from results",
    )
    parser.add_argument(
        "--noise-percentile",
        type=float,
        default=80.0,
        help="Percentile used for noise thresholds (60-95)",
    )
    parser.add_argument(
        "--noise-method",
        default="flat+block",
        choices=["var_flat", "wavelet_var", "jpeg_block", "flat+block"],
        help="Noise detection rule",
    )
    parser.add_argument(
        "--noise-list",
        help="Write per-file noise metrics to CSV",
    )
    parser.add_argument(
        "--noise-move-dir",
        help="Move noisy files to this directory instead of dropping",
    )
    parser.add_argument(
        "--max-noise-sample",
        type=int,
        default=5000,
        help="Maximum number of images used to estimate noise thresholds",
    )
    parser.add_argument(
        "--extensions",
        nargs="*",
        help="Optional list of file extensions to include",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=0,
        help="Random seed used for sampling",
    )
    return parser.parse_args(argv)


def configure_logging() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


def iter_image_paths(root: Path, extensions: Optional[Iterable[str]]) -> List[Path]:
    exts = {e.lower() for e in extensions} if extensions else IMG_EXTENSIONS
    paths: List[Path] = []
    for dirpath, _dirnames, filenames in os.walk(root):
        for name in filenames:
            path = Path(dirpath) / name
            if path.suffix.lower() in exts:
                paths.append(path)
    paths.sort()
    return paths


def read_image(path: Path) -> Optional[np.ndarray]:
    try:
        data = np.fromfile(str(path), dtype=np.uint8)
        if data.size == 0:
            return None
        img = cv2.imdecode(data, cv2.IMREAD_COLOR)
        return img
    except Exception:
        return None


def percentile(values: Sequence[float], q: float) -> float:
    if not values:
        return 0.0
    return float(np.percentile(np.asarray(values, dtype=np.float32), q))


def percentile_optional(values: Sequence[float], q: float) -> Optional[float]:
    if not values:
        return None
    return float(np.percentile(np.asarray(values, dtype=np.float32), q))


def sample_paths(paths: Sequence[Path], max_count: int, seed: int) -> List[Path]:
    if len(paths) <= max_count:
        return list(paths)
    rng = random.Random(seed)
    return sorted(rng.sample(list(paths), max_count))


def ensure_directory(path: Path) -> None:
    if not path.exists():
        path.mkdir(parents=True, exist_ok=True)


def unique_target(directory: Path, filename: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / filename
    if not target.exists():
        return target
    stem = target.stem
    suffix = target.suffix
    counter = 1
    while True:
        candidate = directory / f"{stem}_{counter}{suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


def compute_thresholds_with_cap(paths: Sequence[Path], q_blur: float, q_noise: float, cap: int, seed: int) -> Thresholds:
    cap = max(1, cap)
    samples = sample_paths(paths, max_count=min(len(paths), cap), seed=seed)
    blur_scores: List[float] = []
    var_flat_scores: List[float] = []
    jpeg_scores: List[float] = []
    wavelet_scores: List[float] = []

    for path in samples:
        img = read_image(path)
        if img is None:
            continue
        try:
            result = compute_blur_with_gray(img)
            blur_scores.append(result.score)
            noise = noise_scores_from_gray(result.gray)
        except Exception:
            continue
        var_flat_scores.append(noise["var_flat"])  # type: ignore[arg-type]
        jpeg_scores.append(noise["jpeg_block"])  # type: ignore[arg-type]
        if noise["wavelet_var"] is not None:
            wavelet_scores.append(noise["wavelet_var"])  # type: ignore[arg-type]

    blur_thr = percentile(blur_scores, q_blur)
    thr = {
        "var_flat": percentile(var_flat_scores, q_noise),
        "jpeg_block": percentile(jpeg_scores, q_noise),
        "wavelet_var": percentile_optional(wavelet_scores, q_noise),
    }
    return Thresholds(blur=blur_thr, noise=thr)


def evaluate_image(path: Path, thresholds: Thresholds, args: argparse.Namespace) -> ImageMetrics:
    img = read_image(path)
    if img is None:
        logging.warning("Failed to read image: %s", path)
        return ImageMetrics(path=path, blur_score=0.0, noise_scores={"var_flat": None, "wavelet_var": None, "jpeg_block": None}, decision="error", reason="error")

    result = compute_blur_with_gray(img)
    noise = noise_scores_from_gray(result.gray)

    blur_threshold = thresholds.blur
    blur_is_low = result.score < blur_threshold

    noise_thresholds = thresholds.noise
    noise_method = args.noise_method

    reason = "keep"
    decision = "keep"

    if blur_is_low:
        decision = "blurry"
        reason = "blurry(laplacian)"
    else:
        noisy = is_noisy(noise, noise_thresholds, method=noise_method)
        if noise_method == "wavelet_var" and noise.get("wavelet_var") is None:
            noisy = False
            reason = "skipped(no_wavelet)"
        if noisy:
            decision = "noisy"
            trigger_reason = None
            if noise_method in ("var_flat", "flat+block"):
                var_thr = noise_thresholds.get("var_flat")
                if var_thr is not None and noise.get("var_flat") is not None and noise["var_flat"] > var_thr:
                    trigger_reason = "var_flat"
            if noise_method in ("jpeg_block", "flat+block"):
                jpeg_thr = noise_thresholds.get("jpeg_block")
                if jpeg_thr is not None and noise.get("jpeg_block") is not None and noise["jpeg_block"] > jpeg_thr and trigger_reason is None:
                    trigger_reason = "jpeg_block"
            if noise_method == "wavelet_var":
                wave_thr = noise_thresholds.get("wavelet_var")
                if wave_thr is not None and noise.get("wavelet_var") is not None and noise["wavelet_var"] > wave_thr:
                    trigger_reason = "wavelet_var"
            reason = f"noisy({trigger_reason or noise_method})"
    return ImageMetrics(path=path, blur_score=result.score, noise_scores=noise, decision=decision, reason=reason)


def process_images(args: argparse.Namespace) -> List[ImageMetrics]:
    root = Path(args.input)
    if not root.is_dir():
        raise SystemExit(f"Input directory not found: {root}")

    paths = iter_image_paths(root, args.extensions)
    if not paths:
        logging.info("No images found under %s", root)
        return []

    if not (60 <= args.noise_percentile <= 95):
        raise SystemExit("--noise-percentile must be between 60 and 95")

    thresholds = compute_thresholds_with_cap(paths, args.blur_percentile, args.noise_percentile, args.max_noise_sample, args.seed)

    logging.info(
        "Blur threshold (p=%.1f): %.4f", args.blur_percentile, thresholds.blur
    )
    logging.info(
        "Noise thresholds (p=%.1f): var_flat=%.4f, wavelet_var=%s, jpeg_block=%.4f",
        args.noise_percentile,
        thresholds.noise["var_flat"] if thresholds.noise["var_flat"] is not None else 0.0,
        "{:.4f}".format(thresholds.noise["wavelet_var"]) if thresholds.noise["wavelet_var"] is not None else "None",
        thresholds.noise["jpeg_block"] if thresholds.noise["jpeg_block"] is not None else 0.0,
    )

    results: List[ImageMetrics] = []
    noisy_entries: List[Tuple[Path, Dict[str, Optional[float]]]] = []

    move_dir = Path(args.noise_move_dir).resolve() if args.noise_move_dir else None
    if move_dir:
        ensure_directory(move_dir)

    keep_count = 0
    blurry_count = 0
    noisy_count = 0
    error_count = 0

    for path in paths:
        metrics = evaluate_image(path, thresholds, args)
        results.append(metrics)

        if metrics.decision == "blurry":
            blurry_count += 1
            if args.drop_blurry:
                continue
        elif metrics.decision == "noisy":
            noisy_count += 1
            noisy_entries.append((path, metrics.noise_scores))
            if move_dir:
                target = unique_target(move_dir, path.name)
                ensure_directory(move_dir)
                shutil.move(str(path), target)
                continue
            if args.drop_noisy:
                continue
        elif metrics.decision == "error":
            error_count += 1
            continue
        keep_count += 1

    logging.info(
        "Summary: keep=%d blurry=%d noisy=%d errors=%d",
        keep_count,
        blurry_count,
        noisy_count,
        error_count,
    )

    if logging.getLogger().isEnabledFor(logging.DEBUG) and noisy_entries:
        noisy_entries.sort(key=lambda item: (item[1].get("var_flat") or 0.0), reverse=True)
        for path, scores in noisy_entries[:10]:
            logging.debug(
                "Noisy: %s var_flat=%.4f jpeg_block=%.4f wavelet_var=%s",
                path,
                scores.get("var_flat", 0.0) or 0.0,
                scores.get("jpeg_block", 0.0) or 0.0,
                "{:.4f}".format(scores["wavelet_var"]) if scores.get("wavelet_var") is not None else "None",
            )

    if args.noise_list:
        write_noise_csv(args.noise_list, results)

    return results


def write_noise_csv(path: str, results: Sequence[ImageMetrics]) -> None:
    header = ["path", "var_flat", "wavelet_var", "jpeg_block", "decision", "reason"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        for metrics in results:
            scores = metrics.noise_scores
            writer.writerow(
                [
                    str(metrics.path),
                    f"{scores.get('var_flat'):.6f}" if scores.get("var_flat") is not None else "",
                    f"{scores.get('wavelet_var'):.6f}" if scores.get("wavelet_var") is not None else "",
                    f"{scores.get('jpeg_block'):.6f}" if scores.get("jpeg_block") is not None else "",
                    metrics.decision,
                    metrics.reason,
                ]
            )


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    configure_logging()
    process_images(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
