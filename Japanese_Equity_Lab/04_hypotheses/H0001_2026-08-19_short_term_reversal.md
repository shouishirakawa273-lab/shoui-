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

## 実行結果とEvidence該当性に関する重要な注記(2026-08-19、final skeptic-review反映)

**この一連の実行(Train/Validation/Locked Test全て)はJ-Quants公式APIへ
接続できないセッション制約(EGRESS_BLOCKED)下での合成Fixtureデータに
よるSmoke Run(Pipeline配線・Infrastructure Validation)であり、
投資判断のEvidenceとして使用してはならない。** 実データでのLocked Test
実行は、ユーザー自身のPC上でこのHypothesis/Preregistrationをそのまま
使って別途行う必要がある。

さらに、この特定のSmoke Runには以下の限界がある(final skeptic-reviewの
MEDIUM Finding):Fixtureの3銘柄(7203/6758/9984)のうち7203は単調増加
系列のためSignalが一度も発火せず、Train/Validation/Locked Testの
いずれも実質的に**9984銘柄1つのみ・3トレードのみ**のBacktestになった
(`stock_by_stock_distribution`で確認)。したがって、このSmoke Runの
結果は「市場全体を横断したReversal効果の検証」ではなく、Pipeline
Mechanics(Preregistration固定・Split分離・Locked Test隔離・
Reproducibility記録)が最後まで正常に動くことの確認に限定される。

Locked Test結果自体(`excess_return`)はPreregistrationの
Falsification Condition(`excess_return <= 0`)を満たした
(=この仮説はこのSmoke Run上では支持されなかった)。Conclusionの詳細は
`06_backtests/`配下のExperiment Record、およびPhase5 v1 Completion
Reportを参照。

## Alternative Explanations(Preregistration側に記録、参照用に転記)

1. 単なる取引コスト以下のノイズである可能性(平均回帰は統計的ノイズでも
   頻繁に観測されうる)。
2. 特定の対象期間・対象銘柄への依存であり、市場全体には一般化できない
   可能性(Overfitting/Sample-specific effect)。

## Falsification Condition

Locked Test期間で `excess_return` が0以下であれば、この仮説は支持されない。
