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
**このRoundでも変更しない**(Phase5 v1.1要件§6)。

**重要(D0066参照)**: このGuideのD節・E節の期間設計は、あなたの
ローカル環境で**既に`PREREG0001_R1`として`PREREGISTERED`状態で
固定済み**(`git pull`前の旧Version Scriptで`--step preregister`を
実行してしまったが、内容自体はこのGuideの設計と一致するため、その
まま正式なPreregistrationとして採用した)。したがって**E節の
`--step preregister`コマンドは再実行しない**こと(既に記録済みの
`preregistration_id`と衝突するため、再実行しても`AppendOnlyViolation
Error`にはならず「既に記録済み」を表示して何もしない安全設計だが、
本来不要な操作)。次に打つべきコマンドはF節の`--step train`から。

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

**既に判明している制約(あなたが実行したCoverage Checkより)**:

| Request範囲 | 結果 |
|---|---|
| 2022-01-04 〜 2022-12-30 | 取得成功 |
| 2025-01-06 〜 2025-12-30 | 取得成功 |
| 2021-01-04 〜 2021-12-30 | HTTP 400 |
| 2020-01-06 〜 2021-12-30 | HTTP 400 |
| 2015-01-05 〜 2025-12-30 | HTTP 400 |

ユーザー認識では契約プラン(Light)が過去約5年分のみ履歴提供という
制約。ただしこれは**ユーザー報告であり、J-Quants公式ドキュメントで
このセッションが確認したものではない**(公式Docへの接続自体が
EGRESS_BLOCKED)。上表の「結果」列のみがこのRepositoryが直接確認した
Observed API Behaviorであり、「過去5年」という数字はUser-reported Plan
Constraintとして区別して扱う(DECISIONS.md D0065参照)。

**マルチイヤーRequestは既に確認済み(D0066)**: `_load_real_price_
data()`は`train_period_start`から**そのSplit自身のend_session**まで
を1回のRequestでJ-Quantsへ要求する設計のため、Locked Test実行時には
Train開始日(2022-01-04)からLocked Test終了日(2025-12-30)までの
約4年分が単一のRequestになる。以前はこれが未確認だったが、あなたが
ローカルで以下を実行済み:

```powershell
python scripts\phase5_v1_1_h0001_real_data.py --step coverage-check `
    --codes 7203 6758 8056 3626 `
    --start 2022-01-04 --end 2025-12-30
```

**結果(D0066)**: 4銘柄すべて978 sessions、missing_open=0、
missing_close=0、TOPIX 978 bars、6758のCorporate Action 1件検出、
4銘柄すべてPIT Universe eligible。HTTP 400は発生しなかった
(Strategy Return/Signal件数はこの段階でも一切確認していない)。
この確認結果に基づき`PREREG0001_R1`が固定された(D節・D0066参照)。

出力される`bar_count`/`first`/`last`/`missing_open`/`missing_close`・
Corporate Action件数・TOPIX Bar件数・`PIT universe as_of=...`の
`eligible`銘柄数を確認する。**この出力を見てTrain/Validation/Locked
Testの期間・パラメータを最適化してはならない**(§8/§11)。

## D. 対象期間・銘柄の選定(データ提供制約 + RESEARCH_RULES.mdの制約を守る)

**期間設計(D0065で設計、D0066の経緯により`PREREG0001_R1`として
既にFreeze済み)**:

- Train: 2022-01-04 〜 2023-12-29(約2年)
- Validation: 2024-01-04 〜 2024-12-30(約1年)
- Locked Test: 2025-01-06 〜 2025-12-30(約1年、単独Requestとして既に
  取得成功を確認済みの範囲と一致)

Locked Test=2025年は独立に取得成功を確認済みの範囲を優先して固定した。
残る2022-2024の2年をTrain(2年)/Validation(1年)に配分した理由は
「学習データを検証データより多く確保する」一般的な慣行以上のResult
依存根拠は無い(境界日を2023-12-29/2024-01-04以外にする積極的な理由も
無い、DECISIONS.md D0065参照)。

Chronological・非重複・Locked Test分離という設計原則(Preregistration
の`__post_init__`が構造的に強制)は満たすが、**この期間は
`RESEARCH_RULES.md`の「燃え尽きた期間」記録(2022-01-04〜
2024-12-30・同じ7203/6758/8056/3626・20営業日Momentum→60営業日保有)
とTrain+Validation期間の日付・銘柄が両方とも完全に一致する**
(片方だけでなく両軸とも一致 — これは弱いRisk統制ではないため、
下のQ節の代わりとして扱わないこと)。H0001はMechanism(5営業日
Reversal・10営業日保有)が異なるため「燃え尽きた期間」の定義
(期間・銘柄・Strategyパラメータの組み合わせ全体)には技術的には
該当しないが、データ提供期間の制約上これ以上の分離は不可能(利用可能な
実データが約4年分しかなく、燃え尽きた期間と同じ範囲しか残っていない)。
この重複はskeptic-reviewerに明示的に確認させた結果、「技術的には
Rule違反ではないが、日付軸・銘柄軸のいずれか一方でも独立していれば
残る未見性が両軸一致により完全に失われている」という結論に至った
(DECISIONS.md D0065参照)。**将来のConclusion Recordは、この
ticker+period二重重複を1文で明示し、Evidence Strengthを真の
Out-of-Sample Testより弱く扱うことを明記すること**(H節のChecklist
項目として必須化)。

**銘柄選定**: 7203/6758/8056/3626は引き続き使用する。この4銘柄は
Universe選定として独立した根拠(流動性・時価総額等)を持たないという
既知の限界(Phase5 v1.1 D0064で既出)は変わらない。より広いPIT
Universeから機械的に選定する代替案はD0065で検討したが、このRoundでは
実施しない(Backlog、理由: 新しいUniverse選定能力の追加はこのRoundの
Scope外)。

**Preregistrationは一度Freezeしたら書き換えない**こと。書き換えたく
なったら新しい`preregistration_id`で`revise()`する必要がある。

## E. Preregistration(既にFreeze済み、D0066)

**このStepは既に完了している。再実行しないこと。**

`PREREG0001`(Phase5 v1の合成FixtureによるSmoke Run Preregistration)
を`Preregistration.revise()`した`PREREG0001_R1`(`parent_
preregistration_id=PREREG0001`)が、`06_backtests/preregistrations.
jsonl`へ`PREREGISTERED`状態で既に記録されている(D節の期間・
Universe・`DC0002_JQUANTS_REAL_V1`・実TOPIX・`lookback_days=5`/
`holding_period_days=10`/`excess_return`と一致することを確認済み、
D0066)。`primary_metric`/`parameters`/`falsification_condition`は
親からそのまま引き継がれ、変更されていない(§6/§22)。

もし誤って以下を再実行しても、`preregistration_id`が既に記録済み
であるため`step_preregister()`は「既に記録済み」を表示して何も
書き込まずに終了する(安全、ただし不要な操作なので実行しないこと):

```powershell
python scripts\phase5_v1_1_h0001_real_data.py --step preregister `
    --codes 7203 6758 8056 3626 `
    --train-start 2022-01-04 --train-end 2023-12-29 `
    --validation-start 2024-01-04 --validation-end 2024-12-30 `
    --locked-test-start 2025-01-06 --locked-test-end 2025-12-30
```

**この内容は既に固定されている。Locked Test結果を見るまではこの
内容を変更しないこと。**

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
- Train標本が約2年・Validation約1年・Locked Test約1年という
  比較的短い履歴であること自体は`LIMITED_REAL_DATA_WINDOW`として
  Evidence Limitationに記録すること(D0065参照、他Sourceで長期履歴が
  取得できない限りこのRoundでは解消できない)。
- **(必須、skeptic-reviewer MEDIUM Finding対応)** `unique_entry_dates`
  と`trade_count`を比較すること(RESEARCH_RULES.md「Sample Metricsの
  用語とholding期間の重複」節)。`unique_entry_dates`が`trade_count`
  より著しく少ない場合、それは「多数の独立した検証」ではなく「少数の
  市場局面への賭け」であることをConclusion Recordに明記する。4銘柄・
  10営業日保有という設計はこの重複が起こりやすい形状であるため、
  他Checklist項目より優先して確認すること。
- **(必須、skeptic-reviewer MEDIUM Finding対応)** Conclusion Recordは、
  D節で述べたTicker重複(7203/6758/8056/3626)とPeriod重複
  (2022-01-04〜2024-12-30がRESEARCH_RULES.mdの燃え尽きた期間と完全
  一致)を**1つの結合した文**として明示すること(片方だけの言及・
  暗黙の言及は不可)。その上でEvidence Strengthを、真のOut-of-Sample
  Testより弱く扱う旨を明記すること。Positive/Negativeいずれの
  Result(H0001が支持されても棄却されても)でもこの記述は省略しない。

## I. Claudeへ貼り戻す内容

エラーが出た場合は、エラーメッセージ全文(**APIキーの値を除いて**)を
貼り付けてもらえれば対応できる。成功した場合は、3 split分の
`trade_count`/`excess_return`/
`stock_by_stock_distribution`/`universe_resolution`の要約を共有して
もらえれば、Research Journal(`12_reports/experiment/`)への反映を
手伝える。**Locked Test結果はUnlock後に初めて見る想定のため、貼り付ける
前に「これは正式なEvidenceとして扱ってよいか(Train/Validationで既に
見えていた傾向の延長でしかないか)」を一度確認してから共有すること。**
