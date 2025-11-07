import csv
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np

from utils.noise import noise_scores
from utils import cv2_stub as cv2


def create_clean_and_noisy_images() -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(42)
    base = np.full((256, 256), 128, dtype=np.float32)
    base[64:192, 64:192] = 210
    base[::32, :] = 40
    base[:, ::32] = 40
    clean = np.stack([base] * 3, axis=-1).astype(np.uint8)
    noise = rng.normal(0, 20, clean.shape).astype(np.float32)
    noisy = np.clip(clean.astype(np.float32) + noise, 0, 255).astype(np.uint8)
    return clean, noisy


def test_noise_metrics_distinguish_clean_and_noisy(tmp_path: Path) -> None:
    clean, noisy = create_clean_and_noisy_images()

    scores_clean = noise_scores(clean)
    scores_noisy = noise_scores(noisy)
    assert scores_noisy["var_flat"] > scores_clean["var_flat"]

    # Encode noisy image as JPEG with low quality to amplify blocking artifacts
    success, encoded = cv2.imencode(".jpg", noisy, [int(cv2.IMWRITE_JPEG_QUALITY), 30])
    assert success
    jpeg_noisy = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
    assert jpeg_noisy is not None

    scores_clean_png = noise_scores(clean)
    scores_jpeg = noise_scores(jpeg_noisy)
    assert scores_jpeg["jpeg_block"] > scores_clean_png["jpeg_block"]


def write_image(path: Path, array: np.ndarray) -> None:
    success = cv2.imwrite(str(path), array)
    assert success


def test_cli_noise_integration(tmp_path: Path) -> None:
    clean, noisy = create_clean_and_noisy_images()

    blurry = clean.copy()
    blurry = cv2.GaussianBlur(blurry, (31, 31), 5)

    clean_path = tmp_path / "clean.png"
    noisy_path = tmp_path / "noisy.png"
    blurry_path = tmp_path / "blurry.png"

    write_image(clean_path, clean)
    write_image(noisy_path, noisy)
    write_image(blurry_path, blurry)

    csv_path = tmp_path / "scores.csv"

    cmd = [
        sys.executable,
        "main.py",
        "--input",
        str(tmp_path),
        "--drop-noisy",
        "--noise-percentile",
        "70",
        "--noise-list",
        str(csv_path),
    ]

    completed = subprocess.run(cmd, check=True, capture_output=True, text=True)

    assert "Noise thresholds" in completed.stdout or "Noise thresholds" in completed.stderr

    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    assert any(row["decision"] == "noisy" for row in rows if row["path"].endswith("noisy.png"))
    assert any(row["decision"] == "blurry" for row in rows if row["path"].endswith("blurry.png"))
    assert any(row["decision"] == "keep" for row in rows if row["path"].endswith("clean.png"))
