# DupSnap — UI Update
## 追加
- グループ選択時に横並び比較（サムネカード）を表示
- 類似しきい値(Hamming)をUIスライダーで変更 → 再スキャンで反映
- 自動選択：重複/類似グループは「最大解像度を残す」→ それ以外は削除チェック

## 起動
python -m venv venv
venv\Scripts\activate
python -m pip install -U pip
pip install -r requirements.txt
python run.py

## Noise filtering
The command-line interface now supports filtering noisy photos in addition to blur
detection. Noise is estimated using three complementary metrics:

- **var_flat** – pixel variance in flat regions after removing edges with a Sobel mask.
- **wavelet_var** – variance of the first-level wavelet detail coefficients (requires
  `pywt`, otherwise skipped).
- **jpeg_block** – average absolute difference along 8×8 JPEG grid lines as a proxy
  for blockiness.

Thresholds are computed automatically from a percentile of the analysed images. A
higher percentile makes the filter stricter. Combine the noise options with the
existing blur percentile for best results, e.g.:

```
python main.py --input images --drop-noisy --noise-percentile 80 --noise-list noise.csv \
    --blur-percentile 20
```

Suggested starting values:

- `--blur-percentile 20`
- `--noise-percentile 80`

The `--noise-list` option exports the per-file metrics and decisions to a CSV, which
helps inspect borderline cases. Use `--noise-move-dir <path>` to relocate noisy files
instead of simply dropping them from the results.
