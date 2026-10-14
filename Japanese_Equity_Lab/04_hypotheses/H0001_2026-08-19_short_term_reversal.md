# H0001: Short-term Reversal(短期反転)

`lib.schemas.hypothesis.Hypothesis` / `hypothesis_id=H0001` に対応する。
Phase5 v1 Hypothesis Validation Pipelineの最初のHypothesis(D0062参照)。

## 選定理由

D0061 Phase5 Readiness Gateにより、Phase5 v1で使用可能なDataはPrice
(Adjusted OHLCV)とPIT Universeのみに限定された(Fundamentals/Positioning/
News/Macro/Consensus等は全てForbidden)。既存の`lib.strategies.
fixed_pipeline_validation`(20営業日Momentum→60営業日保有、Pipeline配線
確認専用でInvestment Evidenceではない)と機構的に対称だが符号が逆の、
単純・低パラメータ数のRuleを選ぶことで、Phase5 v1が要求する「Simple・
Deterministic・Interpretable・低パラメータ数」の制約を満たしつつ、
RESEARCH_RULES.mdが既に記録している「燃え尽きた期間」
(2022-01-04〜2024-12-30・7203/6758/8056/3626・20営業日Momentum→
60営業日保有)とはMechanism・パラメータ・対象期間の全てで意図的に区別する。

候補として短期Momentum継続・出来高関連Ruleも検討したが、Reversalは
Mean Reversion文献で広く議論される単純な効果であり、Entry/Exit定義が
対称(`<0`/`>0`のような単一Threshold)で恣意的なCherry-pickを避けやすい
ため選定した(Phase5 v1要件§10-12)。

## Claim

直近5営業日Trailing Close-to-Close Returnが負の銘柄は、その後平均的に
TOPIX対比で超過リターンを生む(短期Reversal)。

## Mechanism

短期的な過剰反応(overreaction)の反転。個人投資家のPanic Selling・
機関投資家のポジション調整などによる一時的な価格圧力が、数営業日のうちに
解消される、という仮説。

## Universe

Phase5 v1要件によりPrice + PIT Universeのみ使用(東証PIT Universe、
`lib.universe`)。Fundamentals/Positioning/News/Macro/Consensus等は
一切使用しない。

## Signal Definition

直近5営業日(`lookback_days=5`)のTrailing Close-to-Close Returnが負。

## Entry Rule / Exit Rule / Holding Period

- Entry: シグナル発生日の翌営業日始値で買い(NEXT_SESSION_OPEN、
  `lib.backtest.engine`の既存Execution Model)。
- Exit: 10営業日後(`holding_period_days=10`)の始値で手仕舞い。
- Holding Period: 10営業日。

## Benchmark

TOPIX(Price Return、`lib.backtest.benchmark`)。

## Success / Failure Metric

- Success: TOPIX比 `excess_return` > 0 (Locked Test期間)。
- Failure: TOPIX比 `excess_return` <= 0 (Locked Test期間)。

## Required Data

- J-Quants Price (Adjusted OHLCV)
- PIT Universe(`lib.universe`)

## Status

`DRAFT` -> `LOCKED`(このRoundで`lock()`を実行、`locked_terms_hash`は
Preregistration Record側に記録)。Preregistration(`PREREG0001`)を固定した
上でTrain/Validation/Locked Testを実行済み(結果は下記「実行結果と
Evidence該当性に関する重要な注記」参照)。

## 実行結果とEvidence該当性に関する重要な注記(更新: 2026-08-19、Phase5 v1.1実データ最終監査反映)

### Synthetic Smoke Run(Phase5 v1、`PREREG0001`)

この一連の実行(Train/Validation/Locked Test全て)はJ-Quants公式APIへ
接続できないセッション制約(EGRESS_BLOCKED)下での合成Fixtureデータに
よるSmoke Run(Pipeline配線・Infrastructure Validation)であり、
投資判断のEvidenceとして使用してはならない。Fixtureの3銘柄
(7203/6758/9984)のうち7203は単調増加系列のためSignalが一度も発火せず、
Train/Validation/Locked Testのいずれも実質的に**9984銘柄1つのみ・
3トレードのみ**のBacktestになった。Locked Test結果自体(`excess_
return`)はPreregistrationのFalsification Condition(`excess_return
<= 0`)を満たした(=この仮説はこのSmoke Run上では支持されなかった)。

### Real-Data Experiment(Phase5 v1.1、`PREREG0001_R1`、DECISIONS.md D0067)

**上記Smoke Runとは別に、実際のJ-Quants Price + PIT Universeデータで
H0001-R1のTrain(2022-01-04〜2023-12-29)/Validation(2024-01-04〜
2024-12-30)/Locked Test(2025-01-06〜2025-12-30、7203/6758/8056/3626)
を実行済み。** Locked Test excess_returnは`+0.00459`(Falsification
Condition `<= 0` を満たさず、この仮説はこのRoundでは棄却されない)。
ただし以下の理由によりConclusionは`PARTIALLY_SUPPORTED`(SUPPORTEDでは
ない)とした。詳細・根拠は`12_reports/experiment/BT_PHASE5_V1_1_H0001_
R1_2026-08-19_report.md`とDECISIONS.md D0067を参照:

- Excess Return幅(0.01%〜0.46%)はVolatility(5.2%〜6.2%)・Max
  Drawdown(-22%〜-36%)に比べて非常に小さく、有意性検定(標準誤差・
  信頼区間)が計算されておらず、Noiseとの識別ができない。
- Preregistrationの`primary_metric`(`excess_return`)は構造的に
  取引コスト計算前(`transaction_cost_adjusted_return`とは独立)で
  あり、このRoundでは`commission_bps`/`slippage_bps`=0のまま実行した
  (Cost前提の変更は行っていない)。現実的な取引コストを仮定すると
  符号が反転しうる。
- Train+Validation期間(2022-01-04〜2024-12-30)はRESEARCH_RULES.mdの
  「燃え尽きた期間」記録と日付・銘柄が完全に一致する(Mechanism・
  パラメータは異なるため技術的にはRule違反ではないが、独立性は弱い)。
- Universe解決状況が全SplitでPARTIAL(`survivorship_bias_unresolved`)
  であり、Survivorship Bias防止を保証できていない。
- 銘柄単位のTrade件数・Trade集中度・Sector Benchmarkは現行Schemaでは
  再現できない(`stock_by_stock_distribution`は平均Returnのみ保持)。

**Conclusion**: `PARTIALLY_SUPPORTED`。BUY/SELL判断ではない。

## Alternative Explanations(Preregistration側に記録、参照用に転記)

1. 単なる取引コスト以下のノイズである可能性(平均回帰は統計的ノイズでも
   頻繁に観測されうる)。
2. 特定の対象期間・対象銘柄への依存であり、市場全体には一般化できない
   可能性(Overfitting/Sample-specific effect)。

## Falsification Condition

Locked Test期間で `excess_return` が0以下であれば、この仮説は支持されない。
