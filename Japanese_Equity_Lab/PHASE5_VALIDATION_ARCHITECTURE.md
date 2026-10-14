# Phase5 v1 Hypothesis Validation Pipeline Architecture

このDocumentは`lib/research/`の設計判断をまとめる。実装詳細は各Module
のdocstringを参照し、ここでは全体像とModuleを跨いだ設計判断のみを記す。
個別Roundの経緯・Reviewer Findings・Conclusionは`DECISIONS.md`
(D0061/D0062)と`12_reports/experiment/`を参照。

## 目的とScope

**「儲かる戦略を発見すること」ではなく「仮説を事前登録し、PIT-safeな
Dataset Contractを固定し、Train/Validation/Locked Testを分離し、1つの
単純な仮説をEnd-to-Endで検証できるReproducible Falsifiable Research
Pipelineを構築・実証すること」**が目的(Phase5 v1要件§1)。成功は
「戦略が儲かったかどうか」ではなく、以下全てが揃うことで定義される:
Preregistration不変性・Dataset Contract明示性・厳密な時系列Split・
Locked Testの一度限りのUnlock・Benchmark比較・事前登録Primary
Metric・Pre-run/Final両方のReviewer Pass・否定的/不確定な結果も正直に
記録すること。

D0061 Phase5 Readiness Gateにより、v1で使用可能なDataは**Price
(Adjusted OHLCV) + PIT Universeのみ**に制限された。Fundamentals/
Disclosures/Positioning/Macro/Global Market/News/Consensus/Evidence
Pathは全てForbidden(`lib.research.preregistration.
DEFAULT_FORBIDDEN_CAPABILITIES`)。

## モジュール構成(`lib/research/`)

- **`preregistration.py`**: `Preregistration`。既存
  `lib.schemas.hypothesis.Hypothesis`のLOCK-based Immutability
  Patternをそのまま踏襲(専用の新規Immutability機構は作らない)。
  `Hypothesis`が持つ claim/mechanism/entry_rule等は複製せず
  `hypothesis_id`で参照し、Phase5固有の追加要件(Research Question・
  Alternative Explanations・Falsification Condition・Train/
  Validation/Locked Test期間・Primary/Secondary Metric・Allowed
  Adjustments・Forbidden Capabilities)のみを追加で固定する。
  `__post_init__`で3期間のChronological Non-overlapを構造的に強制
  (Train終了 < Validation開始、Validation終了 < Locked Test開始、
  Random Split禁止)。`preregister()`でCore Fields SHA-256 Hashを
  固定し、`assert_not_mutated()`で改ざん検知、`revise()`で新IDの
  派生版を作る(元のRecordは一切変更しない)。
- **`dataset_contract.py`**: `DatasetContract`。データ取得元・PIT
  機構・調整方法・欠損/コーポレートアクション/上場廃止の扱いを宣言する
  だけで、データ自体は保持しない。`contract_hash()`で内容のHashを
  取り、`Experiment.dataset_contract_hash`として記録する。
- **`locked_test.py`**: `AccessStage`(RESEARCH_RULES.md「Hidden Test
  隔離」Roadmapが既に定めていた`RESEARCH -> VALIDATION -> LOCKED_TEST
  -> FUTURE_PAPER_TRADE`をそのまま実装)。`LockedTestGate`は
  Unlock済みExperiment IDを記憶し、再Unlockを拒否する(一度見た
  Locked Testは以後純粋なHidden Testとして再利用しない、RESEARCH_
  RULES.mdの「燃え尽きた期間」原則と同じ趣旨)。`FileBackedLockedTest
  Gate`はUnlock Audit RecordをJSON Lines追記専用で永続化し、
  Experimentごとに別プロセス(別コマンド実行)になるこのLabの運用
  形態でもUnlock状態を保つ。
- **`registry.py`**: `PreregistrationRegistry`。既存`lib.registry.
  experiment_registry.ExperimentRegistry`と全く同じJSON Lines追記
  専用Patternをそのまま踏襲(重複ID拒否、削除/上書きAPIは提供しない)。
- **`runner.py`**: `run_split()`。新規Backtest Engineは作らず既存
  `lib.backtest.engine.BacktestEngine`(D0034/D0035/D0037/D0038で
  確立済みのPIT-safe実行機構)をそのまま呼ぶ薄いWrapper。追加する
  制約は3つ: (1) Preregistration状態Gate(PREREGISTERED以前は実行
  不可)、(2) Locked Test Gate(`DataSplit.TEST`はUnlock必須)、
  (3) Split境界Gate(`SplitBoundaryLeakageError`、呼び出し側が渡す
  Trading Calendar/Benchmark BarsがそのSplit自身のend_sessionより
  先の日付を含んでいれば即座に失敗させる — Pre-run PIT Auditで
  実際に発見されたBugへの恒久対策、DECISIONS.md D0062参照)。

## Extend-not-fork(既存Schemaの拡張)

`lib.schemas.experiment.Experiment`へ`preregistration_id`/
`dataset_contract_hash`(共にOptional、既定None)を追加しただけで、
並行する新Record型は作らない。既存のPhase1〜3 Experiment・
`ExperimentRegistry`のJSON Lines形式との後方互換を保つ。

## PIT Source of Truth(D0057境界の維持)

Phase5 v1は`lib.evidence.*`(`filter_usable_at()`含む)へ一切接続
しない(D0057は未解決のまま、このRoundでは解決しない)。PIT判定の
唯一の実行系は`BacktestEngine` + `PointInTimeRecord` + PIT Universe
のみ(D0061 K節のPIT Source of Truth推奨をそのまま踏襲)。

## Test方針

`13_tests/test_research_validation_pipeline.py`(VAL-001〜VAL-027)は
実装の詳細ではなく、Phase5 v1 kickoff要件が明示的に述べた原則
(Preregistrationは実行前に固定される・Random Split禁止・Locked Test
は一度しかUnlockできない・Split境界を越えたPrice参照は拒否される・
Evidence Pathへは接続しない、等)から期待される振る舞いを検証する。
`13_tests/test_short_term_reversal_strategy.py`はH0001固有のSignal
計算(`lib/strategies/short_term_reversal.py`)を検証する。

## 最初のExperiment(H0001)と既知の限界

`04_hypotheses/H0001_2026-08-19_short_term_reversal.md` /
`12_reports/experiment/BT_PHASE5_V1_H0001_SMOKE_V2_2026-08-19_
report.md`参照。このセッションはJ-Quants公式APIへ接続できない
(EGRESS_BLOCKED)ため、実行した一連のTrain/Validation/Locked Testは
合成Fixtureデータ(`13_tests/fixtures/synthetic_jquants_v2_bars.json`)
によるSmoke Run(Pipeline配線・Infrastructure Validationが目的)で
あり、**投資判断のEvidenceではない**。実データでのLocked Test実行は
ユーザー自身のPC上で別途行う必要がある
(`PHASE5_V1_LOCAL_VALIDATION_GUIDE.md`参照)。
