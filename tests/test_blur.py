from __future__ import annotations

import csv
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import cv2
import numpy as np

from utils.blur import blur_scores, is_blurry


def make_checkerboard(size: int = 256, tile: int = 16) -> np.ndarray:
    rows = np.arange(size)[:, None]
    cols = np.arange(size)[None, :]
    board = ((rows // tile + cols // tile) % 2) * 255
    board = board.astype(np.uint8)
    return cv2.cvtColor(board, cv2.COLOR_GRAY2BGR)


def make_text_image(size: int = 256) -> np.ndarray:
    image = np.zeros((size, size, 3), dtype=np.uint8)
    cv2.putText(image, "TEST", (10, size // 2), cv2.FONT_HERSHEY_SIMPLEX, 2.2, (255, 255, 255), 4)
    return image


def blur_image(image: np.ndarray, sigma: float = 2.0) -> np.ndarray:
    return cv2.GaussianBlur(image, (0, 0), sigma)


def test_metrics_ordering_and_classification():
    sharp_cb = make_checkerboard()
    blur_cb = blur_image(sharp_cb)
    sharp_txt = make_text_image()
    blur_txt = blur_image(sharp_txt)

    sharp_scores = blur_scores(sharp_cb)
    blur_scores_cb = blur_scores(blur_cb)
    sharp_text_scores = blur_scores(sharp_txt)
    blur_text_scores = blur_scores(blur_txt)

    assert sharp_scores["vol"] > blur_scores_cb["vol"]
    assert sharp_scores["hfr"] > blur_scores_cb["hfr"]
    assert sharp_text_scores["vol"] > blur_text_scores["vol"]
    assert sharp_text_scores["hfr"] > blur_text_scores["hfr"]

    vol_vals = [sharp_scores["vol"], blur_scores_cb["vol"]]
    hfr_vals = [sharp_scores["hfr"], blur_scores_cb["hfr"]]
    thr = {"vol": float(np.median(vol_vals)), "hfr": float(np.median(hfr_vals))}

    assert not is_blurry(sharp_scores, thr, method="vol+hfr")
    assert is_blurry(blur_scores_cb, thr, method="vol+hfr")


def test_cli_blur_pipeline(tmp_path: Path):
    images_dir = tmp_path / "images"
    images_dir.mkdir()

    sharp = make_text_image()
    blurred = blur_image(sharp)

    sharp_path = images_dir / "sharp.png"
    blurred_path = images_dir / "blurred.png"

    cv2.imwrite(str(sharp_path), sharp)
    cv2.imwrite(str(blurred_path), blurred)

    csv_path = tmp_path / "scores.csv"

    cmd = [
        sys.executable,
        "-m",
        "main",
        "--input",
        str(images_dir),
        "--blur-percentile",
        "50",
        "--drop-blurry",
        "--blur-list",
        str(csv_path),
    ]
    result = subprocess.run(cmd, check=True, capture_output=True, text=True)
    assert csv_path.exists()

    with csv_path.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))

    assert len(rows) == 2
    decisions = {Path(row["path"]).name: row for row in rows}
    assert decisions["sharp.png"]["decision"] == "keep"
    assert decisions["blurred.png"]["decision"] == "blurry"
    assert "vol" in decisions["sharp.png"] and decisions["sharp.png"]["vol"]

    assert result.returncode == 0
