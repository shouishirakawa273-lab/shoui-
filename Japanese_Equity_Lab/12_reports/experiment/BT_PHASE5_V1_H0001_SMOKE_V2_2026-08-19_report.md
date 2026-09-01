# BT_PHASE5_V1_H0001_SMOKE_V2 — Research Journal / Conclusion Record

Phase5 v1 Hypothesis Validation Pipelineの最初のEnd-to-End Experiment。
H0001(`04_hypotheses/H0001_2026-08-19_short_term_reversal.md`)、
Preregistration `PREREG0001`(`06_backtests/preregistrations.jsonl`)、
DECISIONS.md D0062参照。

**このExperimentは投資判断のEvidenceではない。** J-Quants公式APIへ
接続できないセッション制約(EGRESS_BLOCKED)下での合成Fixtureデータに
よるSmoke Run(Pipeline配線・Infrastructure Validationが目的)。

## Facts

- Hypothesis: 直近5営業日Trailing Close-to-Close Returnが負の銘柄は、
  その後平均的にTOPIX対比で超過リターンを生む(短期Reversal)。
- Dataset: 合成Fixture(`13_tests/fixtures/synthetic_jquants_v2_bars.json`)、
  銘柄7203/6758/9984、Benchmark TOPIX_SYNTH、2026-01-05〜2026-07-03。
- Split: Train 2026-01-05〜03-04 / Validation 2026-03-05〜05-01 /
  Locked Test 2026-05-05〜07-03(厳密な時系列3分割)。

## Unknowns(事前に明記)

- 合成Fixtureは実際の株価ではなく、経済的な意味を持たない。
- Fixtureの7203は単調増加系列のため、5営業日Trailing Returnが負に
  なることが構造的に無い(選定後に判明した限界、D0062 #5)。

## Hypothesis / Alternative Explanations(Preregistration固定)

1. 単なる取引コスト以下のノイズである可能性。
2. 特定の対象期間・対象銘柄への依存であり、市場全体には一般化できない
   可能性(Overfitting/Sample-specific effect)。

## Prediction / Falsification Condition(Preregistration固定)

Locked Test期間で`excess_return`が0以下であれば、この仮説は支持されない。

## Result(実測値、`06_backtests/experiment_registry.jsonl`より)

| Split | trade_count | signal_count | excess_return | benchmark_return | win_rate | max_drawdown |
|---|---|---|---|---|---|---|
| Train | 3 | 37 | -0.005693 | 0.003183 | 0.0 | -0.007513 |
| Validation | 3 | 42 | -0.005680 | 0.003146 | 0.0 | -0.007583 |
| **Locked Test** | **3** | **44** | **-0.005666** | **0.003105** | **0.0** | **-0.007665** |

3 splitとも、Signalを生成したのは**9984銘柄1つのみ**
(`stock_by_stock_distribution`が全splitで`{"9984": ...}`のみ)。7203/6758は
一度もSignalを発火しなかった(final skeptic-review MEDIUM Finding)。
Multiple Testing分母: このRoundで検証したHypothesisは1個(H0001)、
Preregistrationは1版(`revise()`なし)、パラメータ探索は無し
(`lookback_days=5`/`holding_period_days=10`固定)。

## Negative Evidence(保持、削除しない)

- Locked Test `excess_return = -0.005666` <= 0 → **Falsification
  Conditionが成立した**(仮説はこのSmoke Run上では支持されなかった)。
- Train/Validation/Locked Testの3 splitとも一貫して`excess_return`が
  負・`win_rate=0.0`であり、都合の良い一部のSplitのみを取り上げられる
  状態ではない(Cherry-pick不可、final skeptic-review確認済み)。
- 3 splitとも実質的に単一銘柄(9984)・3トレードのみのBacktestであり、
  「市場全体を横断したReversal効果の検証」としては成立していない。

## Allowed Adjustments(実際の適用)

`allowed_adjustments`(Transaction Cost前提の変更のみ許可)は、Train/
Validation完了後、一切適用しなかった(`commission_bps`/`slippage_bps`は
既定値のまま)。Preregistrationの他のCore Fieldsも一切変更していない
(`06_backtests/preregistrations.jsonl`に1版のみ存在、`revise()`なし)。

## Reviewer Findings(独立再検証済み、Main Claudeが適用)

- Pre-run pit-auditor: **BLOCKER**(Split境界を越えたPrice参照Bug)→
  修正済み・再監査でCLEAN確認(DECISIONS.md D0062-D.1)。
- Pre-run skeptic-reviewer: **PASS_WITH_CONCERNS**。MEDIUM
  (`lookback_days`のPreregistrationとの一致が構造的に未保証)→修正済み
  (D0062-D.2)。LOW×3(Alternative Explanationsの一般性・Threshold
  選定根拠の薄さ・Fixture Universe Coverageの弱さ)→Preregistration
  固定後のため`revise()`せずBacklog化(D0062-D.3〜5)。
- Final pit-auditor(post-Locked-Test): **CLEAN**(Unlock機構の正当性・
  Split境界の正しさ・Feature/Target計算のPIT安全性・Forbidden Data
  Capability不使用・Reproducibility Fingerprintの整合性、全て確認)。
- Final skeptic-reviewer(post-Locked-Test): **PASS_WITH_CONCERNS**。
  MEDIUM(単一銘柄[9984]への実質的な依存を明記すべき)→本Report・
  H0001.mdへ明記して対応。LOW(H0001.md自体に「投資判断のEvidenceでは
  ない」旨の明記が無かった)→H0001.mdへ追記して対応。

## Conclusion

**INSUFFICIENT_EVIDENCE**(SUPPORTED / PARTIALLY_SUPPORTED /
INCONCLUSIVE / CONTRADICTEDのいずれでもない、この状態自体が正直な
結論)。

理由: (1) Preregistrationの`Falsification Condition`は文字通り成立して
おり(`excess_return <= 0`)、この一点のみを見れば「支持されなかった」
という解釈は可能。しかし(2)このExperimentは合成Fixtureデータであり、
実際の市場を一切代表しない。(3)3 splitともSignalが実質的に単一銘柄
(9984)からしか発生しておらず、n=1銘柄・3トレードという極小サンプルの
下での結果は、Reversal効果という市場全体の仮説について何も主張できない
(final skeptic-review MEDIUM Finding)。したがって「CONTRADICTED」
(仮説が反証された)と結論するのは、この合成データが持ち得ない
説明力を認めることになり過大な主張である。この結果が示すのは
「Falsification Conditionは合成データ上で機械的に成立した」という
事実のみであり、Short-term Reversal仮説そのものへのEvidenceとしては
**INSUFFICIENT_EVIDENCE**とするのが最も誠実な結論である。

**実データでのLocked Test実行は別途必要**(Local Validation Guide、
D0063以降で言及)。その際は本ReportのUnknowns/Negative Evidenceを
引き継ぎ、特にUniverse Coverage(複数銘柄でSignalが実際に発火するか)
を優先確認すること。

## Reproducibility

- `preregistration_id`: `PREREG0001`(全split共通)
- `dataset_contract_hash`: `10272a7fdb4aeb788355bd23e3ec5714596e56d49362fe81494201a23fc219f4`(全split共通)
- `strategy_hash`: 全split共通(`06_backtests/experiment_registry.jsonl`参照、
  パラメータが一切変更されていないことの直接証拠)
- `code_commit`: TRAIN/VALIDATION実行時と、D0062修正適用後のLocked Test
  実行時とでcommitが異なる(修正の反映を意味する、`reproducibility`
  フィールド参照)。
- 同一Snapshot・同一Commit・同一Config・同一Seed(このPipelineは
  Deterministicで乱数を使わない)であれば同一結果になることを、
  修正後のTrain再実行(`censored_count`が0→4へ変化=修正が実際に
  適用されたことの直接証拠)で確認済み。
