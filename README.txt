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
