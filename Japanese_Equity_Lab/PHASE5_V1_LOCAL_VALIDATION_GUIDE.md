# PHASE5_V1_LOCAL_VALIDATION_GUIDE.md — H0001-R1の実データ実行手順

## なぜこの手順が必要か

このセッションはJ-Quants公式APIへ接続できない(EGRESS_BLOCKED、
`api.jquants.com:443`/`jpx.gitbook.io:443`双方でCONNECTがPolicy Denial
(403)により拒否されることをProxy Status Endpoint経由で確認済み、
`DECISIONS.md` D0062/D0064参照)。そのため`scripts/phase5_v1_short_term_
reversal.py`(合成Fixture専用)で実行した一連のTrain/Validation/Locked
Testは、**Smoke Run(Pipeline配線・Infrastructure Validationであり、
投資判断のEvidenceではない**
(`12_reports/experiment/BT_PHASE5_V1_H0001_SMOKE_V2_2026-08-19_
report.md`参照)。

H0001(Short-term Reversal)を実データで検証するPhase5 v1.1では、
**`scripts/phase5_v1_1_h0001_real_data.py`という専用Script(既存
`lib.research.*`をそのまま再利用、新規Backtest Engineは無し)を新規に
実装・Test済み**にした。以下はこのScriptをネットワーク接続可能な
あなたのローカル環境で実行するための手順。Hypothesis(`H0001`)自体・
Signal定義・パラメータ(`lookback_days=5`/`holding_period_days=10`)は
**このRoundでは変更しない**(Phase5 v1.1要件§6)。

このScriptは`Japanese_Equity_Lab/13_tests/test_phase5_v1_1_real_data_
script.py`(REALVAL-002/003/006/007/009/010相当、`JQuantsAdapter`の
Dependency Injection Pointを使った非ネットワークTest)で検証済み。
実際にNetwork Callを行うのはあなたのローカル実行時のみ。

## A. 同期コマンド

```powershell
git fetch origin claude/investment-strategy-pipeline-jyfby5
git checkout claude/investment-strategy-pipeline-jyfby5
git pull
```

## B. APIキー有無の安全な確認(値は表示しない)

```powershell
if ($env:JQUANTS_API_KEY) {
    "API key is set"
} else {
    "API key is NOT set"
}
```

未設定なら`.env`(リポジトリルート、`.gitignore`対象)へ
`JQUANTS_API_KEY=<あなたのAPIキー>`を設定する(`LOCAL_DATA_FETCH_
GUIDE.md`手順1-2と同じ)。Scriptの`main()`は起動時に`load_dotenv()`を
呼ぶため、`.env`に設定しておけば別途環境変数へExportしなくてよい。

## C. Real Data Coverage Check(Preregistration前、Strategy Returnは一切見ない)

Phase5 v1.1要件§8。この段階では行/日付Coverage・欠損Bar・PIT Universe
件数のみを見る。Strategy Return・Signal件数は一切計算しない
(`step_coverage_check()`のTest`test_realval003_*`で構造的に保証済み)。

```powershell
cd shoui-
python scripts\phase5_v1_1_h0001_real_data.py --step coverage-check `
    --codes 7203 6758 8056 3626 `
    --start 2015-01-05 --end 2025-12-30
```

出力される`bar_count`/`first`/`last`/`missing_open`/`missing_close`・
Corporate Action件数・TOPIX Bar件数・`PIT universe as_of=...`の
`eligible`銘柄数を確認する。**この出力を見てTrain/Validation/Locked
Testの期間・パラメータを最適化してはならない**(§8/§11)。

## D. 対象期間・銘柄の選定(RESEARCH_RULES.mdの制約を守る)

`RESEARCH_RULES.md`の「燃え尽きた期間」記録により、**2022-01-04〜
2024-12-30・銘柄7203/6758/8056/3626・固定Strategy(20営業日Momentum→
60営業日保有)の組み合わせは、既に結果を観測済みのため「未見のHidden
Test」として再利用できない。** H0001は別Mechanism(Reversal・
5営業日/10営業日)だが、疑わしきは避ける観点から、対象銘柄
またはTrain/Validation/Locked Test期間の少なくとも一方をこの組み合わせ
とは変えることを推奨する。以下は一例(Cで確認したReal Data Coverageに
基づき調整して構わないが、**一度`--step preregister`を実行したら
書き換えない**こと。書き換えたくなったら新しい`preregistration_id`で
`revise()`する必要があり、それは新しいScript改修が必要になる):

- Train: 2015-01-05 〜 2019-12-30
- Validation: 2020-01-06 〜 2021-12-30
- Locked Test: 2025-01-06 〜 2025-12-30

## E. Preregistrationを固定する(実データ用、既存PREREG0001から`revise()`で派生)

```powershell
python scripts\phase5_v1_1_h0001_real_data.py --step preregister `
    --codes 7203 6758 8056 3626 `
    --train-start 2015-01-05 --train-end 2019-12-30 `
    --validation-start 2020-01-06 --validation-end 2021-12-30 `
    --locked-test-start 2025-01-06 --locked-test-end 2025-12-30
```

内部では`PREREG0001`(Phase5 v1の合成FixtureによるSmoke Run
Preregistration)を`Preregistration.revise()`し、`preregistration_id=
PREREG0001_R1`・`parent_preregistration_id=PREREG0001`として
`06_backtests/preregistrations.jsonl`へ追記する(親Recordは一切変更
されない、Phase5 v1.1要件§5)。`primary_metric`/`parameters`
(`lookback_days=5`/`holding_period_days=10`)/`falsification_condition`
は親からそのまま引き継がれ、変更されない(§6/§22)。

**この時点でPreregistrationは固定される。Locked Test結果を見るまでは
この内容を変更しないこと。**

## F. Train/Validationを実データで実行する

各Splitについて、Scriptは自動的に`train_period_start`から**そのSplit
自身のend_session**までのデータのみをJ-Quantsから取得する(`run_split()`
の`SplitBoundaryLeakageError`により、越えていれば実行時に即座に失敗する
— DECISIONS.md D0062参照)。

```powershell
python scripts\phase5_v1_1_h0001_real_data.py --step train --codes 7203 6758 8056 3626
python scripts\phase5_v1_1_h0001_real_data.py --step validation --codes 7203 6758 8056 3626
```

各実行は標準出力へ`trade_count`/`signal_count`/`excess_return`/
`benchmark_return`/`stock_by_stock_distribution`を表示し、
`06_backtests/experiment_registry.jsonl`へ`BT_PHASE5_V1_1_H0001_R1_
TRAIN`/`BT_PHASE5_V1_1_H0001_R1_VALIDATION`として記録する
(Experiment.notesにUniverse Snapshot Resolution(PIT Universeの
Survivorship Bias解決状況)のSummaryも含まれる)。

## G. Locked Testを一度だけUnlockして実行する

Train/Validationの結果を確認し、`allowed_adjustments`(Transaction
Cost前提のみ)以外は一切変更しないと決めたら:

```powershell
python scripts\phase5_v1_1_h0001_real_data.py --step unlock-locked-test `
    --reason "Train/Validation完了、Final Review実施" --actor "<あなたの名前>"

python scripts\phase5_v1_1_h0001_real_data.py --step locked-test --codes 7203 6758 8056 3626
```

`unlock-locked-test`は同じ`experiment_id`(`BT_PHASE5_V1_1_H0001_R1`)
に対して二度目を呼ぶと`LockedTestAccessError`になる(意図的、Knowledge
Contamination防止)。`06_backtests/locked_test_audit_real.jsonl`
(Phase5 v1の`locked_test_audit.jsonl`とは別File)に記録される。

## H. 期待される観測(Falsifiable Checklist)

- Train/Validation/Locked Testそれぞれで`trade_count`>0(0ならUniverse
  ・期間・Signal定義を再確認、パラメータは変更しない)。
- 3 splitとも`stock_by_stock_distribution`が複数銘柄にまたがっている
  こと(Smoke Runでは単一銘柄[9984]のみだった限界が実データでは解消
  されているはず、`12_reports/experiment/`のSmoke Run Reportと比較)。
- `Experiment.notes`の`universe_resolution=[...]`が`RESOLVED`である
  こと(`PARTIAL`/`UNRESOLVED`/`DATA_UNAVAILABLE`や
  `survivorship_bias_unresolved`が出た場合、実データの`/v2/equities/
  master`のDelisting Field網羅性を疑うこと — pit-auditorのLOW Finding
  参照)。
- `censored_count`が各splitのHolding Period・データ密度に応じて妥当な
  範囲であること(0のままなら境界処理を疑う)。
- Locked Test実行時に`SplitBoundaryLeakageError`/`LockedTestAccessError`
  が出ないこと(出たらG節の手順を再確認)。

## I. Claudeへ貼り戻す内容

エラーが出た場合は、エラーメッセージ全文(**APIキーの値を除いて**)を
貼り付けてもらえれば対応できる。成功した場合は、3 split分の
`trade_count`/`excess_return`/`stock_by_stock_distribution`/
`universe_resolution`の要約を共有してもらえれば、Research Journal
(`12_reports/experiment/`)への反映を手伝える。**Locked Test結果は
Unlock後に初めて見る想定のため、貼り付ける前に「これは正式なEvidence
として扱ってよいか(Train/Validationで既に見えていた傾向の延長でしか
ないか)」を一度確認してから共有すること。**
