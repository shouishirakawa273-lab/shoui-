# LOCAL_DATA_FETCH_GUIDE.md — 実J-Quantsデータでの検証手順(Phase3A)

## なぜこの手順が必要か

この開発セッション(クラウド環境)はネットワークポリシーにより`api.jquants.com`を含む
外部APIへ一切疎通できない(`api.jquants.com` / Yahoo Finance / `example.com`いずれも
CONNECTが403で拒否されることを確認済み、`DECISIONS.md` D0012・D0025参照)。そのため
Phase3Aの「実J-Quantsデータを投入してもPipelineがEnd-to-Endで動作するか」という検証は、
**ネットワーク接続可能なあなたのローカル環境で以下を実行して初めて完了する。**

このセッションでは代わりに、手作業で用意したJ-Quants形状のscratch dataで
`--source local`の配管そのものが動くことまでは確認済み(Phase3A完了報告参照)。
実際のJ-Quantsレスポンスの検証はまだ行われていない。

## 手順1: `.env`を設定する(ローカル環境のみ)

リポジトリルートの`.env`(`.gitignore`対象、コミットしない)に、J-Quants契約の
リフレッシュトークンを設定する。

```
JQUANTS_REFRESH_TOKEN=<あなたのリフレッシュトークン>
```

**絶対にこの値をコミットしない・ログに出さない・チャットに貼らない。**

## 手順2: 実データを取得してローカルへ保存する

`scripts/fetch_jquants_local_snapshot.py`を実行する。これは`lib/data_sources/jquants.JQuantsAdapter`
(エンドポイント名・レート制限・認証フローはこのAdapterと共通)を使って実際にJ-Quantsへ
接続し、結果を`lib/data_sources/local_snapshot.LocalSnapshotAdapter`が読める
ファイル形式で`Japanese_Equity_Lab/01_data/raw/local_snapshot_input/`
(`.gitignore`対象)へ保存する。トークンやIDトークンはファイルへ一切書き出さない。

```bash
cd shoui-  # リポジトリルート
python scripts/fetch_jquants_local_snapshot.py \
    --codes 7203 6758 8056 3626 \
    --benchmark-index-code 0000 \
    --start 2022-01-04 --end 2024-12-30
```

引数の考え方:

- `--codes`: Phase3Aで指定された最小Universe(トヨタ7203 / ソニー6758 / BIPROGY8056 /
  TOKAIホールディングス3626)。技術的な理由(例: カレンダー突合・出来高0日の確認など)で
  1〜2銘柄追加してよいが、無闇に増やさないこと(Phase3Aの目的はPipeline検証であって
  多銘柄スクリーニングではない)。
- `--benchmark-index-code`: TOPIXの index_code は`"0000"`と想定しているが**未検証**。
  もし404等で失敗する場合、J-Quantsの公式ドキュメント/サポートで正しいコードを確認し、
  この引数を差し替えること(`lib/data_sources/jquants.py`のdocstringにも同じ注記あり)。
- `--start` / `--end`: 固定Strategy(20営業日モメンタム→60営業日保有)を複数回
  非重複で検証するには、最低でも1年、できれば2〜3年分の期間を推奨する
  (期間が短すぎるとトレードが1回も成立しない可能性がある)。実際に使った期間は
  Pipeline実行時の標準出力にそのまま記録される。

実行が成功すると、最後に次のPipeline実行コマンドがそのまま表示される。

## 手順3: Pipelineを実行する

手順2の最後に表示されたコマンド、またはそれと同じ引数で以下を実行する。

```bash
python scripts/jquants_lab_pipeline.py --source local \
    --local-snapshot-dir Japanese_Equity_Lab/01_data/raw/local_snapshot_input \
    --codes 7203 6758 8056 3626 --benchmark-index-code 0000 \
    --start 2022-01-04 --end 2024-12-30 \
    --commission-bps 5 --slippage-bps 5
```

これにより実際のJ-Quantsデータで、Raw Snapshot保存(`01_data/raw/local/`) →
Trading Calendar構築 → Adjusted OHLCV変換(株式分割は未調整のまま、
corporate action hintは情報表示のみ) → 固定Strategy実行 → TOPIX Benchmark比較 →
Experiment Registry / Provenance記録、が一本のPipelineとして走る。

## 手順4: 結果を確認する

標準出力に表示される以下を確認する(このセッションでは実データで検証できていない項目)。

1. **corporate action hints**: 対象銘柄・期間に実際に株式分割等があった場合、
   検出件数が意図通りか(1回の分割につき概ね1件になっているか)。0件でも
   異常ではない(対象期間に分割が無かっただけの可能性が高い)。
2. **universe**: `resolution=RESOLVED`になるか、`survivorship_bias_unresolved`が
   Trueになるか(`/listed/info`が`delisting_date`に相当するフィールドを
   返さない場合は自動的にTrueになる、D0028参照)。
3. **execution_outcomes**: `MISSING_PRICE` / `UNEXECUTABLE_NO_OPEN` /
   `OUTSIDE_DATA_RANGE`が異常に多くないか(実データ特有の欠損パターンを検知する)。
4. **reproducibility**: `git_dirty`がFalseの状態(working treeがcleanな状態)で
   同じコマンドを2回実行し、`metrics`が完全に一致するか。

もし途中で`DataSourceError`やフィールド不整合が出た場合は、J-Quantsの実レスポンス形状が
このセッションの推測(`lib/data_sources/jquants.py`・`lib/data_sources/convert.py`の
docstringに記載の前提)と異なっていたことを意味する。エラーメッセージと実際のレスポンス
JSONの構造(**トークン等の認証情報を除いて**)を教えてもらえれば、`convert.py`側だけを
実レスポンスに合わせて修正できる(`BacktestEngine`側の変更は不要な設計になっている)。
