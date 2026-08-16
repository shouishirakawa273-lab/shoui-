# 01_data/

価格・企業データの置き場。**raw dataは原則immutable**(削除ではなく `99_archive/` へ退避)。

- `raw/`: 取得元から得た生データ(未加工)。
- `processed/`: rawから機械的に生成した中間データ。
- `prices/`: `lib/schemas/price_data.RawOHLCVBar` / `CorporateAction` / `AdjustedOHLCVBar`。
  raw OHLCV・corporate actions・adjusted OHLCVは必ず別ファイルで保持する(調整済みだけを残さない)。
- `fundamentals/`: 決算・業績予想等。
- `corporate_events/`: 自社株買い・増配・M&A等のイベント。
- `market/`: TOPIX・日経平均・為替・金利等のマクロ市場データ。
- `sectors/`: 業種指数・セクター分類。
- `point_in_time/`: `lib/point_in_time.PointInTimeRecord` に対応するスナップショット
  (`published_at` / `available_at` を保持し、後から同じバックテストを再現できるようにする)。

ファイル名は `<コード>_<データ種別>_<期間 or 日付>.<拡張子>` を基本とする
(例: `7203_raw_ohlcv_2020-2026.parquet`)。
