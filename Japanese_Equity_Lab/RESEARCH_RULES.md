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
- クラウドの開発セッションは外部APIへ疎通できないことがある(README.md参照)。
  実データでの疎通確認は必ずローカル環境で行う。Pipeline配線の検証には合成データ
  (`13_tests/fixtures/`)を使ってよいが、**実際のデータであるかのように偽装しない**
  (Snapshotの`source`フィールド等で常に区別する)。
- 上記の理由で外部APIへ疎通できない環境では、`lib/data_sources/local_snapshot.LocalSnapshotAdapter`
  (`--source local`)を使う。ユーザーがネットワーク制限のないローカル環境で
  J-Quants API V2から取得したJSON/CSVファイルを、決まった命名規約
  (`equity_bars_<code>.json`、`trading_calendar.json`、`topix_bars.json`、
  `equities_master.json`。詳細は`local_snapshot.py`のモジュールdocstring)で1つの
  ディレクトリへ配置し、`--local-snapshot-dir`で渡す。これは「実データそのもの」を
  扱う経路であり、fixtureのような合成データではないが、**このセッション自身は
  一度もJ-Quantsへ(APIにもドキュメントにも)疎通していない**ため、このAdapterが
  実レスポンスの形状を正しく扱えるかどうかはユーザーがローカルで実行して確認する
  必要がある(D0025〜D0028、D0031〜D0033、`LOCAL_DATA_FETCH_GUIDE.md`参照)。
- 現在の契約プランはLight(ユーザー申告)。`DataSourceCapabilities`
  (`lib/data_sources/base.py`)がLightプランでの利用可否についての未検証の推測を
  保持するが、これは警告目的であり、Adapterは契約プランを理由に`fetch_*`呼び出しを
  事前ブロックしない(実際のAPIが返すエラーをそのまま伝える)。利用不可と判明した
  Datasetを他Providerへsilent fallbackすることは禁止する。

## Pipeline全体の構成 (`scripts/jquants_lab_pipeline.py`)

Data -> Feature -> Signal -> Decision -> Execution -> Return -> Benchmark比較 ->
Experiment Registry を一本のPipelineとして実行できる。

- `lib/data_sources/base.DataSourceAdapter`: 外部データソースへの依存を切り離すInterface
  (J-Quants API V2ベース、Phase3A.1でV1から全面移行)。
  `lib/data_sources/jquants.JQuantsAdapter`(実データ・API直接接続、`x-api-key`認証)、
  `lib/data_sources/local_snapshot.LocalSnapshotAdapter`(実データ・ローカルファイル経由、
  外部APIへ疎通できない環境向け)、`lib/data_sources/fixture.FixtureDataSourceAdapter`
  (合成データ)が同じInterfaceを満たす。個別銘柄日次Bar(`fetch_equity_bars`)に加え、
  TOPIX専用Endpoint(`fetch_topix_bars`)・一般指数(`fetch_general_index_bars`)・
  銘柄マスタ(`fetch_equities_master`)も同じ抽象化で扱う。
- `lib/snapshot.RawSnapshotStore`: APIレスポンスを`01_data/raw/`へImmutableに保存する
  (manifestにsource/endpoint/request_parameters/retrieved_at/data_period/
  response_schema_version/content_hash/local_file/record_countを記録)。
  認証情報らしきキーが混入していたら`SecretLeakageError`で保存を拒否する。
- `lib/data_sources/convert.py`: Raw Payload(J-Quants/fixture共通の形状) ->
  `RawOHLCVBar` / `TradingCalendar` への変換。
- `lib/market_calendar.TradingCalendar`: `next_trading_session` / `previous_trading_session` /
  `is_trading_session` を実データのCalendarから解決する。範囲外の問い合わせは
  `TradingCalendarResolutionError`で失敗させ、土日だけで機械的に代替しない。
- `lib/strategies/fixed_pipeline_validation.py`: Pipeline検証専用の固定Strategy
  (20営業日Price Return > 0 -> 次営業日Open執行 -> 60営業日保有)。
  **パラメータ最適化は禁止。このStrategyの収益性は評価対象ではない。**
- `lib/backtest/engine.BacktestEngine.run()`: 上記を実際に実行し、価格欠損時は
  fallbackせずそのトレードをスキップし、Benchmarkデータが要求期間を全区間
  カバーしない場合は`BenchmarkDataInsufficientError`で失敗する。`price_history`引数は
  `lib/backtest/price_history.PriceHistorySource` Protocol(decision_atごとにPrice
  Historyを取得するInterface)であり、全期間共通の事前計算済みSeriesは保持しない
  (Phase3A.2、D0035)。`StaticPriceHistory`(無調整・fixture向け)と
  `AsOfAdjustedPriceHistory`(Raw + Corporate ActionからPIT-safeに都度構築)の
  2実装があり、`scripts/jquants_lab_pipeline.py`の`--price-adjustment {none,pit}`で
  切り替える。
- `lib/reproducibility.py`: `run_id` / `dataset_hash` / `strategy_hash` / `config_hash` /
  `code_commit` を`Experiment.reproducibility`へ記録し、同一Inputでの再現性を検証できる。
  `Experiment.price_adjustment`(`PriceAdjustmentProvenance`)には
  `adjustment_method` / `as_of_policy` / `corporate_action_source` /
  `raw_snapshot_ids`を記録する(D0035)。

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

### `available_at` と `retrieved_at` を混同しない

`available_at`(市場参加者が当時実際に参照可能になった日時)と、
`lib.data_sources.base.RawFetchResult.retrieved_at`(Research Labがこのデータを
**取得した**日時)は全く別の概念である。混同すると、例えば数年前の株価データを
「今日」取得しただけで当時のバックテストが全て使えなくなる(過度に保守的な誤り)、
あるいは逆に安全確認を誤魔化す方向にも働きうる。`available_at`は常に市場の営業時間
(`lib/market_calendar.py`)から導出し、`retrieved_at`から導出しないこと
(`lib/backtest/engine.py`の実装、および
`13_tests/test_available_at_vs_retrieved_at.py`で確認する)。

### Provider CodeとInternal Codeを混同しない

J-Quants API V2は銘柄コードを5桁で返す(実SmokeTestで確認済み、DECISIONS.md D0036:
内部Code"7203"をrequestすると、Providerは``"Code": "72030"``を返す。末尾1桁は
銘柄種別を表すと考えられ、普通株は"0")。Research Lab内部(Universe定義・
`BacktestRunConfig.universe_codes`・Strategy等)は一貫して4桁の内部Codeを使うため、
`lib/data_sources/convert.py`が変換時に`lib.data_sources.ticker_codes.
normalize_provider_code_to_internal()`で正規化する。無条件に文字列の末尾を削る
実装はしない(確認済みパターンに一致しない場合は例外を送出する)。Raw Snapshotには
Providerの生の値(5桁)がそのまま残り、この正規化とは無関係。`RawOHLCVBar` /
`CorporateAction` / `ListingRecord`は`code`(内部)と`provider_code`(Providerの
生の値)を両方保持し、混同しない。

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

## Sample Metricsの用語とholding期間の重複 (`lib/backtest/engine.py`)

「sample_size」という曖昧な名称は使わない。`BacktestMetrics`は以下を明示的に区別する。
**Policy Skip(意図的な不執行)とExecution Failure(執行の失敗)を同じ「unexecuted」として
合算しない**(次項「Execution Outcome」参照)。

- `signal_count`: `signal_fn`がTrueを返した回数(執行できたかどうかを問わない)。
- `policy_skipped_count`: Portfolio Policyにより最初から執行を試みなかった件数
  (現状は`SKIPPED_POSITION_OPEN`のみ)。失敗ではない。
- `order_attempt_count`: Policy Skipを除いた、実際に執行を試みた件数
  (= `signal_count - policy_skipped_count`)。
- `trade_count` / `executed_count`: 実際にトレードとして成立した数(同じ値)。
- `execution_failed_count`: 執行を試みたが完了できなかった件数
  (= `order_attempt_count - executed_count`)。
- `signal_to_trade_rate`: `executed_count / signal_count`(Policy Skipも分母に含む)。
- `order_execution_rate`: `executed_count / order_attempt_count`(Policy Skipを除いた
  「執行を試みたもの」のうちの成功率)。
- `unique_tickers`: 実際にトレードが成立した銘柄のユニーク数。
- `unique_entry_dates`: 実際の執行(entry)日のユニーク数。

**holding期間が重なるtradeを、統計的に独立なサンプルとして扱わない。** `trade_count`が
大きくても、多くのtradeが同時期に同じ市場環境へエクスポージャーを持っている場合、
実質的な独立サンプル数(有効サンプルサイズ)は`trade_count`よりずっと小さい。
`unique_entry_dates`が`trade_count`に比べて著しく少ない場合、それは「多数の独立した
検証」ではなく「少数の市場局面への賭け」を意味する可能性が高いことを、レポートで
明記すること。`BacktestEngine.run()`は既定で`PositionPolicy.NO_REENTRY_WHILE_POSITION_OPEN`
により同一銘柄の重複建てを防ぐが、複数銘柄が同時にシグナルを出すケース(市場全体の
地合いに従属したシグナル)までは防がない。

## Event StudyとPortfolio Simulationの違い

この2つは目的が異なり、扱いも変える。

- **Event Study**: 個々のシグナル前後のリターンを、ポジションの重なりを気にせず
  統計的に集計する分析手法。同一銘柄・同時期のoverlapping observationsを許容できる
  (例:「決算サプライズ後N営業日のリターン分布」を見る場合、保有していたかどうかは
  関係ない)。ただし**overlapを許容していることを必ず明記する**こと。`compute_metrics()`
  を独自に集めたTradeResult列へ直接適用すればEvent Study用途にも使えるが、
  `unique_entry_dates`と`trade_count`の差からoverlapの程度を確認し、レポートに含める。
- **Portfolio Simulation**: 実際に資金を配分する前提のシミュレーション。
  `BacktestEngine.run()`はこちらであり、デフォルトの Execution/Position Policy は
  `PositionPolicy.NO_REENTRY_WHILE_POSITION_OPEN`(同一銘柄で既にポジションを
  保有している間に出た追加シグナルは新規建てしない、`ExecutionOutcome.SKIPPED_POSITION_OPEN`
  として記録される)。ピラミッディングや複数ポジションの重ね持ちはVer.1では行わない。

## Execution Outcome (`lib/backtest/engine.ExecutionOutcome`)

価格欠損等でトレードが成立しなかった場合もsilent skipせず、必ず結果を記録する。
2つの性質が異なる結末を区別する。

**Policy Skip**(`POLICY_SKIP_OUTCOMES`、失敗ではない):
- `SKIPPED_POSITION_OPEN`: 同一銘柄で既にポジションを保有中のため、シグナルを無視した。

**Execution Failure**(`EXECUTION_FAILURE_OUTCOMES`、執行を試みたが完了できなかった):
- `UNEXECUTABLE_NO_OPEN`: 執行日のOpenが欠損しており、entryできなかった。
- `MISSING_PRICE`: entryはできたが、exit日の価格が欠損しておりcloseできなかった。
- `OUTSIDE_DATA_RANGE`: Trading Calendarのデータ範囲外で執行日/exit日が解決できなかった。

**成功**:
- `EXECUTED`: 正常に約定した。

`BacktestMetrics.execution_outcomes`にExecutionOutcome別の件数を必ず保存し、
`signal_count` / `policy_skipped_count` / `order_attempt_count` / `executed_count` /
`execution_failed_count` / `signal_to_trade_rate` / `order_execution_rate`として
分母を明示する(Multiple Testingの原則をシグナル単位にも適用する)。
`13_tests/fixtures/portfolio_scenario.json`(System Behavior Test専用、Strategy
Performance評価には使わない)で、Policy Skip・Execution Failure・正常Execution/Exitが
それぞれ意図通りに区別されることを確認する(`13_tests/test_portfolio_scenario.py`)。

## Price Data: raw / corporate actions / adjusted の分離 (`lib/schemas/price_data.py`)

調整済み価格だけを保存すると、後から調整方法の誤りに気付けない。以下を必ず分離して保持する。

- `RawOHLCVBar`: 取得元の生の値(書き換えない)
- `CorporateAction`: 株式分割・併合・配当・合併・上場廃止等のイベント
- `AdjustedOHLCVBar`: raw + corporate actionsから再現可能な調整済み系列

Ver.1は株式分割・併合による価格連続性のみを補正し、配当再投資によるTotal Return化は行わない
(次項のBenchmark参照)。

Adjusted OHLCVをFeature生成に使う場合は`apply_split_adjustments_as_of(..., as_of=decision_at)`
を使う。Corporate Actionには2つの異なる時点があり、必ず分離して扱う(D0011参照)。

- `known_at`(= `announced_at`): そのCorporate Actionの「存在」が公知になった時刻。
  Event情報(例:「分割が発表されている」)としてはこの時刻以降利用してよい。
- `adjustable_at`(= `effective_date`の寄付時刻): 実際に株数・価格基準が切り替わる時刻。
  過去Price Seriesの調整は、この時刻を過ぎたCorporate Actionにのみ適用してよい。

例: 8/1に分割発表、8/15が意思決定時点(decision_at)、10/1が分割の効力発生日、の場合。
8/15時点では「将来分割される」というEvent情報は利用できる(`known_at`は過ぎている)が、
10/1の分割はまだ効力が発生していない(`adjustable_at`を過ぎていない)ため、8/15時点の
過去Price Featureを10/1以降の基準へ補正してはならない。「発表されている」ことと
「Price Seriesを調整してよい」ことは別問題である。

`announced_at`が不明、または`as_of`より後に発表される(=まだ公知でない)Corporate Actionが
混入している場合は`LookAheadBiasError`で拒否する(黙って除外しない)。一方、発表済みだが
まだ効力発生前のCorporate Actionは、エラーにはせず単に調整対象から除外する
(意図した挙動であり、データ不備ではない)。Raw priceはこの調整でも一切書き換えない。

### Case A(Announcement Signal)とCase B(Price Series連続化)の分離(Phase3A.1、D0032)

上記の`known_at`/`adjustable_at`の区別に加え、Phase3A.1で用途を明確に2つへ分離した。

- **Case A**: Corporate Action Announcementそのものを取引Signalとして使う用途。
  本物の`announced_at`が必須。`apply_split_adjustments_as_of()`が担う(変更なし)。
- **Case B**: Price Seriesが分割で不連続にならないようにする用途。J-Quants V2の
  `AdjFactor`はCorporate Actionのex-dateのBar行そのものに機械的に付与され、事前の公表を
  経由しない(公式仕様確定、DECISIONS.md D0034)。そのため`announced_at`は不要で、
  その日のBarデータ自体が取得可能になる時刻(`session_close_at(effective_date)`)を
  PIT gateとして使う`build_provider_derived_adjusted_bars()`(`lib/schemas/price_data.py`)
  が担う。計算式(確定):
  `Adjusted Price = Raw Price × Π(そのバー日より後にeffectiveなAdjFactor)`、
  `Adjusted Volume = Raw Volume ÷ Π(同上)`。as_of時点でまだ効力発生日のBarが取得可能に
  なっていないEventは、エラーにはせず黙って調整対象から除外する(Case Aの「未公表」
  ケースとは異なる、通常の時系列進行として扱う)。`ExRT`はCorporate Action /
  ex-right eventのmetadataとして保持するのみで、`AdjFactor == 1`の日にExRTだけが
  存在してもPrice Adjustmentは行わない。

### Price Series連続化(Case B)はPipelineへ統合済み(Phase3A.2、D0035)

Case A(Announcementを使う用途)のデータSourceは引き続き**未実装**(DECISIONS.md D0014、
`announced_at`付きデータSourceが無いため)。Case B(Price Series連続化)は
`build_provider_derived_adjusted_bars()`としてPIT-safeに実装済みで、AdjFactorの
計算方法(乗算/除算の向き含む)も公式仕様として確定している(DECISIONS.md D0034)。

D0034で特定した「`BacktestEngine.run()`が`price_history`を1回だけ事前計算し使い回すため、
単一のas_ofで事前調整するとWalk-Forwardの一部decision_atが未来のCorporate Actionで
調整された価格を見てしまう」という問題は、Phase3A.2で`PriceHistorySource` Protocol
(`lib/backtest/price_history.py`)を導入して解消した(D0035)。`BacktestEngine`は
decision_atごとに`price_history.bars_up_to(code, as_of=decision_at)`を呼ぶため、
全期間共通の事前計算済みSeriesは存在しない。

`scripts/jquants_lab_pipeline.py`は`--price-adjustment {none,pit}`(既定`pit`)で
選択できる。`pit`は`AsOfAdjustedPriceHistory`(decision_atごとのPIT-safe As-of
Adjustment)を、`none`は`StaticPriceHistory`(無調整)を使う。実データBacktestでは
`pit`を推奨する。

`lib/data_sources/convert.detect_corporate_action_events_from_equity_bars()`
(旧`detect_split_hints_from_daily_quotes()`、D0032で置き換え)は、その日の行が
`AdjFactor != 1`または`ExRT`ありであればEvent当日として抽出する。`--price-adjustment pit`
使用時はこのEventがBacktestへ実際に反映される(`--price-adjustment none`では
情報提供のみで、Adjusted価格系列には反映しない)。

## Multiple Testing

AIが多数の戦略を試した場合、良かったものだけを見せてはいけない。
`06_backtests/` の Experiment Registry には常に以下の分母を保存する。

`generated` / `tested` / `rejected` / `pending` / `paper` / `validated`

### Infrastructure Validation Runと戦略性能Testを区別する

Pipeline配線・実データ疎通確認そのものを目的としたRun(Corporate Action処理・
Provider Code正規化・Execution Outcome分類等が正しく動くかの確認)は、戦略性能の
統計的検証(Hidden Test)とは区別する。前者の結果(勝率・リターン等)を見てから
同じ期間・同じ銘柄・同じStrategyパラメータを「未見のTest期間」として扱うと、
実質的にはTest期間を見てから採否を決めていることになり、Look-ahead的な
Overfittingにつながる(RESEARCH_RULES.md冒頭原則「Test期間を見た後に無断で
パラメータを変更しない」と同じ趣旨)。

**燃え尽きた(burned)期間の記録**: 2022-01-04〜2024-12-30・銘柄
(7203/6758/8056/3626)・固定Strategy(20営業日Momentum→60営業日保有)の組み合わせは、
Phase3B開始前のE2E Infrastructure Validation(実J-Quantsデータでの初回End-to-End
Backtest、DECISIONS.md D0037参照)で結果を観測済みである。今後、この期間・銘柄・
Strategyパラメータの組み合わせを「まだ結果を見ていないHidden Test」として扱っては
ならない。Walk-Forward・真のOut-of-Sample検証を行う場合は、この期間とは異なる
期間を新たに設定すること。

## Benchmark: Price Return / Total Return (`lib/backtest/benchmark.py`)

日本株戦略は原則 **TOPIX** を基準Benchmarkとする。可能なら業種指数とも比較する。
「戦略 +10%」ではなく「TOPIX比 +○%」「Sector比 +○%」を重視する。

Ver.1はキャピタルゲイン研究が主目的のため、**Price Return同士の比較を基本とする**。
戦略側のリターンとBenchmark側のリターンで `return_type`(`PRICE_RETURN` / `TOTAL_RETURN`)が
一致しない場合、`compare_to_benchmark()` はエラーにして比較させない
(配当込みTotal Returnとの混同を防ぐ)。

Phase3A.1で`DataSourceAdapter.fetch_topix_bars()`(J-Quants V2の`/v2/indices/bars/daily/topix`、
TOPIX専用Endpoint)へ接続先を変更した(D0031)。Phase3A時点で使っていた`index_code="0000"`の
推測は廃止した(専用Endpointのため銘柄・指数コード指定が不要になった)。レスポンス形状は
個別銘柄Barと同じO/H/L/Cを持つという未検証の前提に立っている。ユーザーがローカルで実際に
叩いた結果、形状が異なると判明した場合は`lib/data_sources/jquants.py`の`fetch_topix_bars()`と
`lib/data_sources/convert.topix_bars_payload_to_raw_bars()`のみを修正すればよい
(Backtest Engine・Benchmark比較ロジックへの影響はない設計)。

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
のInterfaceを定義する。`listing_date` / `delisting_date` / `market` / `sector` /
`tradable_from` / `tradable_until`等から、その時点で投資可能だった銘柄集合を返す。
実データが無い/不十分な場合に架空の補完(「投資可能銘柄が0件だった」等)をせず、
`UniverseResolution`(`RESOLVED` / `PARTIAL` / `UNRESOLVED` / `DATA_UNAVAILABLE`)で明示する。
Phase1.1はInterfaceとsynthetic data向けの素朴な実装(`ListingBasedUniverseProvider`)のみ。

Phase3Aで`/listed/info`(V1)を接続し、Phase3A.1で
`lib/data_sources/convert.equities_master_payload_to_listing_records()`により
J-Quants V2の`/v2/equities/master`へ接続先を変更した(D0033)。`/v2/equities/master`が
`listing_date`/`delisting_date`に相当するフィールドを含むかどうかは未検証であり、
含まれない場合は`None`のまま正直に扱う(数値を推測で埋めない方針)。`ListingRecord`には
`company_name`も追加し、`lib.universe.check_company_name_consistency()`で手入力の
Ticker→会社名対応がMasterと矛盾しないか確認できる(手入力をCanonical Dataとして
扱わない、D0033)。`UniverseSnapshot.survivorship_bias_unresolved`は、
渡された全`ListingRecord`に`delisting_date`が1件も無い場合に自動的に`True`になる
(`_auto_detect_survivorship_bias()`、D0028)。

### `PARTIAL` Resolution(Phase3C、D0038)

`survivorship_bias_unresolved=True`の場合、`UniverseSnapshot.resolution`は
`RESOLVED`ではなく`UniverseResolution.PARTIAL`を返す(Survivorship Biasが残ったまま
「完全に解決できた」と自称しないため)。`PARTIAL`は「Universeの下限(現在まで
生き残った銘柄)は判明しているが、上限(当時存在したが後に廃止された銘柄)は
判明していない」ことを意味する。`PARTIAL`のUniverseを使ったBacktest結果は、実際より
良い成績が出ている可能性がある前提で解釈すること(廃止された銘柄=多くの場合
業績不振や上場廃止基準抵触による銘柄が母集団から欠落しているため)。

### 普通株Universeの明示的な定義(Phase3C、D0038)

`build_common_stock_universe(listings, *, common_stock_market_codes)`で、ETF・REIT・
優先株・インフラファンド等(普通株以外)をUniverseから除外する。
`common_stock_market_codes`(普通株の市場区分を表すMarketCodeの許可リスト)は
呼び出し側が明示的に渡す必要があり、このモジュール自身は実際のJ-Quants MarketCodeの
値・意味を検証・決め打ちしない。許可リストが空、またはMarketCodeが不明な場合は
安全側(除外側)に倒す。現時点(Phase3C)では実際のMarketCode値がこのセッションでは
未検証のため、実データPipeline(`scripts/jquants_lab_pipeline.py`)へはまだ接続していない
(DECISIONS.md D0038)。

### `BacktestEngine`のdecision_atごとのUniverse再解決(Phase3C、D0038)

`BacktestEngine.run(..., universe_provider=...)`を指定すると、`decision_date`ごとに
`universe_provider.as_of(decision_at)`を再解決し(全期間分を一度だけ事前計算して
使い回すことはしない、`PriceHistorySource`のD0035と同じ設計思想)、その時点の
Universeに含まれないCodeについては`signal_fn`自体を呼ばない。省略時は従来通り
`config.universe_codes`をそのまま使う(完全後方互換)。`scripts/jquants_lab_pipeline.py`は
実データSource利用時に`/v2/equities/master`から構築した`universe_provider`を
`engine.run()`へ渡している。

### J-Quants Light Planでの既知の未確認事項(Phase3C、D0038)

- `/v2/equities/master`の`date`パラメータが真のPoint-in-Time Snapshot(廃止銘柄を
  含む)を返すか、単に「現在の状態」を返すだけかは未検証。後者の場合、
  Survivorship Biasは構造的に解消できず`resolution=PARTIAL`が恒常的な状態になる。
  `scripts/fetch_jquants_local_snapshot.py --master-pit-check`で、ローカル環境から
  実際に確認できる(使い方はスクリプトのDocstring参照)。
- 市場区分(Prime/Standard/Growth)は2022年4月のTSE市場再編で大きく変わっており、
  単一時点のMasterスナップショットから過去の市場区分を復元することはできない。
  `ListingRecord.market`は「そのMasterスナップショット自身のas_of時点の区分」を
  表すに過ぎず、過去のdecision_atにおける市場区分としては使わないこと。

## Provenance (`lib/registry/provenance.py`)

すべての重要な知見は生成元まで遡って追跡可能にする。
例: YouTube URL → Comment ID → Idea → Hypothesis → Backtest → Paper Test → Knowledge。
AIの要約と原文は必ず区別して保存する。`ProvenanceStore` は追記専用のリンク台帳で、
`trace_to_origin()` で終点から起点までのchainを取得できる。

## Reproducibility (`lib/reproducibility.py`)

同じRaw Snapshot・同じStrategy version・同じConfig・同じCode versionであれば
同じBacktest結果になることを検証できるよう、`Experiment.reproducibility`
(`ReproducibilityFingerprint`)に以下を記録する。

- `run_id` / `dataset_hash`(使用したRaw Snapshotのcontent_hashから導出) /
  `strategy_hash` / `config_hash`
- `code_commit`: 実行時点のgit commit hash(取得できない場合はNone)
- `git_dirty`: working treeに未コミットの変更があったか(判定不能ならNone)。
  **`git_dirty=True`の場合、`code_commit`が指すコミット内容と実行時のコードが
  完全には一致していない可能性があり、完全な再現性は保証されない。**
  この場合はレポート・Experimentの`notes`等に明記すること。

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
