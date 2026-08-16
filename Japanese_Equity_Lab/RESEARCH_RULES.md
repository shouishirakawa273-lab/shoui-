# RESEARCH_RULES.md

## 0. 最重要方針

**「バックテストで一番儲かった戦略を探す」ことを目的にしない。**
AIで大量の戦略を探索すると、偶然過去データに適合しただけの戦略が高確率で発生する。
したがって以下を絶対原則とする。

1. 仮説をバックテスト前に登録する(`04_hypotheses/`)。
2. 試した戦略は成功・失敗問わず全て保存する。
3. 良い結果だけを選択して表示しない。
4. Train / Validation / Testを分離する。
5. Walk-Forward検証を行う。
6. Point-in-Time Dataを使用する。
7. Look-ahead biasを禁止する。
8. Survivorship biasを可能な限り排除する。
9. 取引コスト・スリッページを考慮する。
10. TOPIX等のBenchmarkと比較する。
11. Sector benchmarkとも比較する。
12. Market / Size / Value / Momentum / Quality / SectorなどへのExposureを可能な範囲で確認する。
13. 一部の銘柄だけで効いていないか分布を見る。
14. 特定年度だけで効いていないか確認する。
15. 直近でも戦略が機能しているか確認する。
16. サンプル数を必ず表示する。
17. 「なぜその戦略が効くのか」という経済的・制度的メカニズムを要求する。
18. 仮説と検証済み知見を明確に分離する。
19. 失敗した仮説もKnowledgeとして残す。
20. 実際の注文は行わない。

## データ入手に関する既知の制約(2026年時点)

- J-Quants無料プランは業績予想データに約12週間の遅延がある。真のリアルタイムPITではなく、
  「当時実際に無料で入手可能だった情報」を模したPITである点を常に明記する。
- 上場廃止銘柄の履歴データは無料ソースでは網羅できないことが多い。
  Survivorship biasを完全には排除できない場合、`09_knowledge/` にその旨を制約として記録する。
- 上記制約はごまかさず、Backtest結果・レポートに明記する。「制約がある」ことを隠さない。

## 東証取引時間 (`lib/market_calendar.py`)

大引け・寄付時刻のハードコードは`lib/market_calendar.py`だけに集約する
(他モジュールに散在させない)。制度変更を反映済み: 東証現物市場の後場終了は
2024-11-05に15:00→15:30へ延長された(`market_close_time()`が日付に応じて切り替える)。
将来また取引時間が変わった場合は、このモジュールだけを更新すればよい。

## Point-in-Time の区別 (`lib/point_in_time.py`, `lib/backtest/engine.py`)

データ側と意思決定側で、日付だけでなく時刻レベルで区別する。

データ側(`PointInTimeRecord`):
- `value_date`: その数値が対象とする期間・時点
- `published_at`: 発表・公開された日時(tz-aware)
- `available_at`: 市場参加者が実際に参照可能になった日時(遅延を考慮、tz-aware)

意思決定側(`DecisionWindow`、3時刻すべてtz-aware):
- `information_used_at`: シグナル生成に使ってよい情報の締め時刻。Point-in-Timeガードは
  この時刻を基準に行う。
- `decision_at`: シグナルを確定した時刻(通常は`information_used_at`と同時刻)。
- `execution_at`: 実際に約定する時刻。

過去時点のバックテストでは「現在知っている情報」ではなく
「その時点で市場参加者が利用可能だった情報」(`available_at <= information_used_at`)のみを使用する。
これは日付単位ではなく時刻単位で判定する。特に**取引時間終了後(大引け後)に公表された
決算・適時開示は、同日の大引け時点の `information_used_at` では利用できない**。
`lib/point_in_time.assert_no_lookahead()` と `lib/backtest/engine.SignalInput` は、
違反したレコードが1件でも渡された場合に `LookAheadBiasError` を送出して拒否する
(黙って除外しない)。

### Close-to-Close Look-ahead防止

`available_at <= information_used_at` だけでは不十分で、「当日Closeの情報でSignalを作り、
同じClose価格で約定する」という現実には実行不可能な取引も防ぐ。Ver.1のデフォルト
Execution Modelは:

```
Daily Closeまでの情報 -> Signal生成(decision_at = 当日大引け) -> 次営業日OpenでExecution
```

`DecisionWindow`は`decision_at`が当日大引け時刻と一致し、かつ`execution_at`が同日中の場合、
`LookAheadBiasError`で構築自体を拒否する。この既定の窓は`build_close_to_next_open_window()`
で組み立てる。特殊なClosing Auction戦略(`ExecutionModel.CLOSING_AUCTION`)は将来別
Execution Modelとして実装する(Ver.1では未対応)。

## Price Data: raw / corporate actions / adjusted の分離 (`lib/schemas/price_data.py`)

調整済み価格だけを保存すると、後から調整方法の誤りに気付けない。以下を必ず分離して保持する。

- `RawOHLCVBar`: 取得元の生の値(書き換えない)
- `CorporateAction`: 株式分割・併合・配当・合併・上場廃止等のイベント
- `AdjustedOHLCVBar`: raw + corporate actionsから再現可能な調整済み系列

Ver.1は株式分割・併合による価格連続性のみを補正し、配当再投資によるTotal Return化は行わない
(次項のBenchmark参照)。

Adjusted OHLCVをFeature生成に使う場合は`apply_split_adjustments_as_of(..., as_of=decision_at)`
を使い、`decision_at`より後に**発表**される(=その時点ではまだ知り得ない)株式分割・併合を
過去のSignal生成に混入させない。判定は`effective_date`ではなく`announced_at`(発表時刻)基準で
行う。`announced_at`が不明なCorporate Actionは`LookAheadBiasError`で拒否する(黙って除外しない)。
Raw priceはこの調整でも一切書き換えない。

## Multiple Testing

AIが多数の戦略を試した場合、良かったものだけを見せてはいけない。
`06_backtests/` の Experiment Registry には常に以下の分母を保存する。

`generated` / `tested` / `rejected` / `pending` / `paper` / `validated`

## Benchmark: Price Return / Total Return (`lib/backtest/benchmark.py`)

日本株戦略は原則 **TOPIX** を基準Benchmarkとする。可能なら業種指数とも比較する。
「戦略 +10%」ではなく「TOPIX比 +○%」「Sector比 +○%」を重視する。

Ver.1はキャピタルゲイン研究が主目的のため、**Price Return同士の比較を基本とする**。
戦略側のリターンとBenchmark側のリターンで `return_type`(`PRICE_RETURN` / `TOTAL_RETURN`)が
一致しない場合、`compare_to_benchmark()` はエラーにして比較させない
(配当込みTotal Returnとの混同を防ぐ)。

## 税金の扱い

Backtest Coreが扱うリターンは、取引コスト・スリッページ控除後・**税引前**
(Net Pre-tax Return)までとする。税引後シミュレーションはVer.1のスコープ外とし、
将来別モジュールとして扱う。

## Hypothesis のライフサイクル (`lib/schemas/hypothesis.py`)

`status`: `DRAFT` → `LOCKED` → `TESTED` → `REJECTED` / `PAPER` → `VALIDATED`

LOCK時に条件(terms)のSHA-256 hash(`locked_terms_hash`)を保存し、
LOCKED以降にtermsが変わっていないかをコードで検証できるようにする(改ざん検知)。
LOCKED後に条件を変更する場合、元のHypothesisは書き換えず、`revise()` で
新しいHypothesis IDを発行し `parent_hypothesis_id` で系譜を残す。

Experiment Registry(`lib/registry/experiment_registry.py`)は追記専用(append-only)で、
`experiment_id` が重複する記録や上書き・削除のAPIを提供しない。

## Strategy Decay

戦略は永遠には機能しない。各Strategyは `ACTIVE` / `WATCH` / `DEGRADED` / `RETIRED` の状態を持ち、
Retirement Criteria(例: 直近12か月Alpha < 0)を登録時に明記する。

## Point-in-Time Universe (`lib/universe.py`)

Survivorship bias排除の前提として、`UniverseProvider`(`as_of(as_of: datetime) -> UniverseSnapshot`)
のInterfaceを定義する。将来`listing_date` / `delisting_date` / `market` / `sector` /
`tradable_from` / `tradable_until`等から、その時点で投資可能だった銘柄集合を返す。
実データが無い/不十分な場合に架空の補完(「投資可能銘柄が0件だった」等)をせず、
`UniverseResolution`(`RESOLVED` / `UNRESOLVED` / `DATA_UNAVAILABLE`)で明示する。
Phase1.1はInterfaceとsynthetic data向けの素朴な実装(`ListingBasedUniverseProvider`)のみ。
実データソースとの接続はPhase2以降。

## Provenance (`lib/registry/provenance.py`)

すべての重要な知見は生成元まで遡って追跡可能にする。
例: YouTube URL → Comment ID → Idea → Hypothesis → Backtest → Paper Test → Knowledge。
AIの要約と原文は必ず区別して保存する。`ProvenanceStore` は追記専用のリンク台帳で、
`trace_to_origin()` で終点から起点までのchainを取得できる。

## 全schema共通のメタデータ (`lib/schemas/base.py`)

将来schemaのフィールドが変わっても追跡できるよう、全schema(`RecordMeta`を継承)は
`schema_version` / `created_at` / `updated_at` / `source` / `provenance_id` を持つ。
値オブジェクトとして扱うため全て `frozen=True` とし、変更は常に
`dataclasses.replace()` で新しいインスタンスを作ることで表現する
(raw dataをimmutableに保つ方針、および`00_config`〜`99_archive`の
「削除ではなく退避する」方針と一致させる)。既存recordを書き換える設計にはしない。

`updated_at`は「このスナップショットが最後に導出・確定した時刻」を表し、永続化済みの
ファイルを直接書き換えて`updated_at`だけ差し替える、という使い方はしない
(詳細は`lib/schemas/base.py`のdocstring)。`record_id` / `record_version` /
`supersedes_record_id` / `content_hash`のような汎用バージョン管理フィールドは
Phase1.1では見送った(DECISIONS.md D0010)。`Hypothesis`は`parent_hypothesis_id` +
`locked_terms_hash`という専用の系譜追跡を既に持つ。
