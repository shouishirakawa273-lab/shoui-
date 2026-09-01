# LOCAL_DATA_FETCH_GUIDE.md — 実J-Quants API V2データでの検証手順(Phase3A.1)

## なぜこの手順が必要か

この開発セッション(クラウド環境)はネットワークポリシーにより`api.jquants.com`・
`jpx.gitbook.io`(公式ドキュメント)を含む外部ホストへ一切疎通できない
(いずれもCONNECTが拒否されることを確認済み、`DECISIONS.md` D0012・D0025・D0031参照)。
そのためPhase3Aの「実J-Quants API V2データを投入してもPipelineがEnd-to-Endで動作するか」
という検証は、**ネットワーク接続可能なあなたのローカル環境で以下を実行して初めて完了する。**

さらに、このAdapterのEndpoint・Field名(V2)は、ユーザーがセッション内で明示した仕様を
Canonical Specificationとして実装したものであり、このセッション自身が公式ドキュメントや
実APIで検証したものではない。実行中にエラーやField不整合が出た場合は、下記「手順4」の
通り実レスポンスの構造を教えてもらえれば`lib/data_sources/convert.py`だけを修正できる
(`BacktestEngine`側の変更は不要な設計になっている)。

現在の契約プランはLight(ユーザー申告)。`daily_prices` / `trading_calendar` / `topix` /
`listed_master`はLightプランでも利用可能と想定しているが未検証(`DataSourceCapabilities`、
DECISIONS.md D0033参照)。利用不可の場合はJ-Quants自身がエラーを返すので、その内容を
そのまま確認できる(他Providerへのsilent fallbackはしない)。

## 手順1: APIキーを取得する

J-Quantsの契約者ダッシュボードでAPI V2用のAPIキーを取得する(V1のリフレッシュトークンとは
別物)。

## 手順2: `JQUANTS_API_KEY`を`.env`へ設定する(ローカル環境のみ)

リポジトリルートの`.env`(`.gitignore`対象、コミットしない)に設定する。

```
JQUANTS_API_KEY=<あなたのAPIキー>
```

既存のScreening Tool(`core/providers/jquants.py`)が使う`JQUANTS_REFRESH_TOKEN`とは
別の変数なので、両方設定しても構わない(`.env.example`参照)。

**絶対にこの値をコミットしない・ログに出さない・チャットに貼らない。**

## 手順3: 最小Smoke Testを行う

まず小さいリクエスト(例: 1銘柄・数日分の`equity_bars`)で疎通確認することを推奨する。

```bash
cd shoui-  # リポジトリルート
python -c "
from dotenv import load_dotenv
load_dotenv()
import sys
sys.path.insert(0, 'Japanese_Equity_Lab')
from datetime import date
from lib.data_sources.jquants import JQuantsAdapter
adapter = JQuantsAdapter()
result = adapter.fetch_equity_bars(codes=['7203'], start_date=date(2026, 1, 5), end_date=date(2026, 1, 9))
print(result.payload[:2])
"
```

エラーが出た場合、エラーメッセージ(**APIキーの値を除いて**)を教えてもらえれば
`lib/data_sources/jquants.py`のEndpoint・パラメータを実際の仕様に合わせて修正できる。

**確認済み事項(DECISIONS.md D0036)**: `result.payload`の``"Code"``フィールドは、
requestした内部Code("7203")ではなく5桁のProvider Code(例: "72030")で返る
(末尾1桁は銘柄種別を表すと考えられ、普通株は"0")。これは想定通りの挙動であり、
`lib/data_sources/convert.py`が変換時に内部Code("7203")へ自動的に正規化するため、
`--codes`引数や`equity_bars_<code>.json`のファイル名は引き続き4桁の内部Codeを使う。

## 手順4: 実データを取得してローカルへ保存する

Smoke Testが通ったら、`scripts/fetch_jquants_local_snapshot.py`を実行する。これは
`JQuantsAdapter`をそのまま使って以下4種類のデータを取得し、
`lib/data_sources/local_snapshot.LocalSnapshotAdapter`が読める形式で
`Japanese_Equity_Lab/01_data/raw/local_snapshot_input/`(`.gitignore`対象)へ保存する。

1. Trading Calendar (`/v2/markets/calendar`)
2. 対象4銘柄のDaily Bars (`/v2/equities/bars/daily`)
3. TOPIX (`/v2/indices/bars/daily/topix`)
4. Listed Issue Master (`/v2/equities/master`)

```bash
python scripts/fetch_jquants_local_snapshot.py \
    --codes 7203 6758 8056 3626 \
    --start 2022-01-04 --end 2024-12-30
```

引数の考え方:

- `--codes`: Phase3Aで指定された最小Universe(トヨタ自動車7203 / ソニーグループ6758 /
  BIPROGY8056 / TIS株式会社3626)。技術的な理由(例: カレンダー突合・出来高0日の確認など)で
  1〜2銘柄追加してよいが、無闇に増やさないこと(Phase3Aの目的はPipeline検証であって
  多銘柄スクリーニングではない)。
- `--start` / `--end`: 固定Strategy(20営業日モメンタム→60営業日保有)を複数回
  非重複で検証するには、最低でも1年、できれば2〜3年分の期間を推奨する
  (期間が短すぎるとトレードが1回も成立しない可能性がある)。実際に使った期間は
  Pipeline実行時の標準出力にそのまま記録される。

実行が成功すると、最後に次のPipeline実行コマンドがそのまま表示される。

## 手順5: Pipelineを実行する

手順4の最後に表示されたコマンド、またはそれと同じ引数で以下を実行する。

```bash
python scripts/jquants_lab_pipeline.py --source local \
    --local-snapshot-dir Japanese_Equity_Lab/01_data/raw/local_snapshot_input \
    --codes 7203 6758 8056 3626 \
    --start 2022-01-04 --end 2024-12-30 \
    --commission-bps 5 --slippage-bps 5
```

これにより実際のJ-Quants V2データで、Raw Snapshot保存(`01_data/raw/jquants_local/`) →
Trading Calendar構築 → Adjusted OHLCV変換(株式分割は未調整のまま、Corporate Action
Eventは情報表示のみ) → 固定Strategy実行 → TOPIX Benchmark比較 → Experiment Registry /
Provenance記録、が一本のPipelineとして走る。

## 手順6: 結果を確認する

標準出力に表示される以下を確認する(このセッションでは実データで検証できていない項目)。

1. **corporate action events**: 対象銘柄・期間に実際に株式分割等があった場合、
   検出件数が意図通りか(1回の分割につき1件になっているか。`AdjFactor`/`ExRT`の
   V2での実際の付与方式が、ユーザー提示仕様通りかを確認する)。0件でも異常ではない
   (対象期間に分割が無かっただけの可能性が高い)。
2. **universe**: `resolution=RESOLVED`になるか、`survivorship_bias_unresolved`が
   Trueになるか(`/v2/equities/master`が`delisting_date`に相当するフィールドを
   返さない場合は自動的にTrueになる、D0028参照)。
3. **company name consistency warnings**: 表示された場合、`CompanyName`フィールドの
   実際の値・意味が想定と異なる可能性がある。
4. **execution_outcomes**: `MISSING_PRICE` / `UNEXECUTABLE_NO_OPEN` /
   `OUTSIDE_DATA_RANGE`が異常に多くないか(実データ特有の欠損パターンを検知する)。
5. **reproducibility**: `git_dirty`がFalseの状態(working treeがcleanな状態)で
   同じコマンドを2回実行し、`metrics`が完全に一致するか。

## 手順7(推奨、必須ではない): AdjFactorの計算結果を実データで確認する

`lib/schemas/price_data.build_provider_derived_adjusted_bars`は、AdjFactorの適用方法
(Ex-dateより前の価格にのみ乗算、出来高は除算)を公式仕様として実装済み
(DECISIONS.md D0034)。実際に分割があった銘柄・期間が見つかった場合、以下を手動で
突き合わせて確認することを推奨する(このセッションは実データで検証できていないため)。

1. その銘柄のAdjFactorが1でない日(=分割のex-date)を`equity_bars_<code>.json`から探す。
2. `build_provider_derived_adjusted_bars`で計算したex-date前日のAdjusted Closeと、
   J-Quantsが返す`AdjC`(その日以降の情報を使って計算された、Provider自身の調整済み値)を
   比較する。ex-date前後を通じて概ね連続した価格になっていることを確認する。
3. HolDiv=2(半休場日)・HolDiv=3(non-business day with holiday trading)を含む期間があれば、
   `is_trading_session()`がそれぞれ意図通り取引日/非取引日と判定するかも確認する。

なお、`build_provider_derived_adjusted_bars`自体は上記の通りPIT-safeに実装済みだが、
`scripts/jquants_lab_pipeline.py`はまだこれを実際のBacktest実行(`price_history`)へは
組み込んでいない。`BacktestEngine.run()`が単一のprice_historyを事前計算してから
複数のdecision_atへ使い回す設計のため、単一のas_ofで事前調整するとWalk-Forwardの
一部decision_atでPIT安全性が崩れうる(decision_atごとの再計算にはEngine側の配線変更が
必要、DECISIONS.md D0034参照)。この配線変更はPhase3B以降の検討事項。

もし途中で`DataSourceError`やフィールド不整合が出た場合は、J-Quants V2の実レスポンス形状が
このセッションの推測(`lib/data_sources/jquants.py`・`lib/data_sources/convert.py`の
docstringに記載の前提)と異なっていたことを意味する。エラーメッセージと実際のレスポンス
JSONの構造(**APIキー等の認証情報を除いて**)を教えてもらえれば、`convert.py`側だけを
実レスポンスに合わせて修正できる(`BacktestEngine`側の変更は不要な設計になっている)。
