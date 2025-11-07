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

## Blur detection CLI

The repository also provides a command line helper that can score images for blur and automatically drop or relocate the softer files. The detector combines Laplacian variance (``vol``), Tenengrad energy and a high-frequency FFT ratio (``hfr``) after normalising each image to a 1024px long side. Typical ``vol`` values for sharp photos range from a few hundred up to several thousand, while ``hfr`` is a fraction between 0 and 1 (higher means sharper).

Key options:

* ``--drop-blurry`` – omit blurry files from further processing.
* ``--blur-percentile`` – percentile (5–50) used to auto-calibrate thresholds per batch.
* ``--blur-method`` – choose ``vol``, ``hfr`` or ``vol+hfr`` (default) for the decision rule.
* ``--blur-list`` – write the per-file metrics and decision into a CSV file.
* ``--blur-move-dir`` – move blurry images into the specified folder instead of keeping them.
* ``--blur-sample-limit`` – limit the number of images sampled when estimating thresholds (default 5000).

Example:

```
python -m main --input images --drop-blurry --blur-percentile 20 --blur-list scores.csv
```

Very dark or high-ISO shots may yield lower scores; consider lowering the percentile or switching to the ``vol`` method if you observe false positives.
