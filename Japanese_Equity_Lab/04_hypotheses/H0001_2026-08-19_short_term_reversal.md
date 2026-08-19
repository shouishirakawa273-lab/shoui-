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
Preregistration Record側に記録)。

## Alternative Explanations(Preregistration側に記録、参照用に転記)

1. 単なる取引コスト以下のノイズである可能性(平均回帰は統計的ノイズでも
   頻繁に観測されうる)。
2. 特定の対象期間・対象銘柄への依存であり、市場全体には一般化できない
   可能性(Overfitting/Sample-specific effect)。

## Falsification Condition

Locked Test期間で `excess_return` が0以下であれば、この仮説は支持されない。
