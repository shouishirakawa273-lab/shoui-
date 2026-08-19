# PHASE5_V1_LOCAL_VALIDATION_GUIDE.md — H0001-R2の実データ実行手順

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

**`PREREG0001_R1`(当初のTrain 2015-2019/Validation 2020-2021/Locked
Test 2025という期間設計)は、あなたが実際にローカルで実行したLocal
Coverage Checkの結果、現在の契約プラン下では取得不能(2021年以前を含む
Requestが一貫してHTTP 400)と判明したため、一度もPreregistration・
Runとして実行しないまま設計段階で放棄した。** 以下は、この制約を踏まえて
再設計した`PREREG0001_R2`の手順(DECISIONS.md D0065参照)。

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

**D節の期間設計を`--step preregister`で固定する前に、必ず以下を追加で
確認すること**(まだ未実行、これもStrategy Returnを見ないCoverage
Checkの一部):

```powershell
cd shoui-
python scripts\phase5_v1_1_h0001_real_data.py --step coverage-check `
    --codes 7203 6758 8056 3626 `
    --start 2022-01-04 --end 2025-12-30
```

これが重要な理由: `_load_real_price_data()`は`train_period_start`から
**そのSplit自身のend_session**までを1回のRequestでJ-Quantsへ要求する
設計になっている。したがってLocked Test実行時には、実際には
Train開始日(2022-01-04)からLocked Test終了日(2025-12-30)までの
**約4年分が単一のRequest**になる。これまで確認できているのは
「単年(2022年・2025年)の単独Request」と「2015年を含む11年分の
Request(失敗、ただし2021年以前を含んでいたため2022年以降のみの
複数年Requestが失敗する理由なのか、単に2021年以前を含んでいたことが
理由なのかを判別できない)」のみであり、**2022年以降だけに限定した
複数年単一Requestが成功するかどうかはまだ未確認**。この確認が
HTTP 400になった場合は、D節の期間案を見直す必要がある(Strategy
Resultには一切影響されない、純粋なAPI到達可否の再設計)。

出力される`bar_count`/`first`/`last`/`missing_open`/`missing_close`・
Corporate Action件数・TOPIX Bar件数・`PIT universe as_of=...`の
`eligible`銘柄数を確認する。**この出力を見てTrain/Validation/Locked
Testの期間・パラメータを最適化してはならない**(§8/§11)。

## D. 対象期間・銘柄の選定(データ提供制約 + RESEARCH_RULES.mdの制約を守る)

**期間設計(D0065、Cのマルチイヤー確認が成功した前提で)**:

- Train: 2022-01-04 〜 2023-12-29(約2年)
- Validation: 2024-01-04 〜 2024-12-30(約1年)
- Locked Test: 2025-01-06 〜 2025-12-30(約1年、単独Requestとして既に
  取得成功を確認済みの範囲と一致)

Chronological・非重複・Locked Test分離という設計原則(Preregistration
の`__post_init__`が構造的に強制)は満たすが、**この期間は
`RESEARCH_RULES.md`の「燃え尽きた期間」記録(2022-01-04〜
2024-12-30・同じ7203/6758/8056/3626・20営業日Momentum→60営業日保有)
とTrain+Validation期間がほぼ完全に重複する**。H0001はMechanism
(5営業日Reversal・10営業日保有)が異なるため「燃え尽きた期間」の
定義(期間・銘柄・Strategyパラメータの組み合わせ全体)には該当しない
が、データ提供期間の制約上これ以上の分離は不可能(利用可能な実データが
約4年分しかなく、燃え尽きた期間とほぼ同じ範囲しか残っていない)。
この重複はskeptic-reviewerに明示的に確認させ、Research-Integrity上
許容可能と判断した根拠をDECISIONS.md D0065に記録している。

**銘柄選定**: 7203/6758/8056/3626は引き続き使用する。この4銘柄は
Universe選定として独立した根拠(流動性・時価総額等)を持たないという
既知の限界(Phase5 v1.1 D0064で既出)は変わらない。より広いPIT
Universeから機械的に選定する代替案はD0065で検討したが、このRoundでは
実施しない(Backlog、理由: 新しいUniverse選定能力の追加はこのRoundの
Scope外)。

**一度`--step preregister`を実行したら書き換えない**こと。書き換え
たくなったら新しい`preregistration_id`で`revise()`する必要がある。

## E. Preregistrationを固定する(実データ用、既存PREREG0001から`revise()`で派生)

```powershell
python scripts\phase5_v1_1_h0001_real_data.py --step preregister `
    --codes 7203 6758 8056 3626 `
    --train-start 2022-01-04 --train-end 2023-12-29 `
    --validation-start 2024-01-04 --validation-end 2024-12-30 `
    --locked-test-start 2025-01-06 --locked-test-end 2025-12-30
```

内部では`PREREG0001`(Phase5 v1の合成FixtureによるSmoke Run
Preregistration)を`Preregistration.revise()`し、`preregistration_id=
PREREG0001_R2`・`parent_preregistration_id=PREREG0001`として
`06_backtests/preregistrations.jsonl`へ追記する(親Recordは一切変更
されない、Phase5 v1.1要件§5)。`primary_metric`/`parameters`
(`lookback_days=5`/`holding_period_days=10`)/`falsification_condition`
は親からそのまま引き継がれ、変更されない(§6/§22)。`PREREG0001_R1`は
Registryに一度も記録されていないため、上書き・改ざんの対象にもならない
(単に使われなかった識別子)。

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
`06_backtests/experiment_registry.jsonl`へ`BT_PHASE5_V1_1_H0001_R2_
TRAIN`/`BT_PHASE5_V1_1_H0001_R2_VALIDATION`として記録する
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

`unlock-locked-test`は同じ`experiment_id`(`BT_PHASE5_V1_1_H0001_R2`)
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

## I. Claudeへ貼り戻す内容

エラーが出た場合は、エラーメッセージ全文(**APIキーの値を除いて**)を
貼り付けてもらえれば対応できる(特にC節のマルチイヤー確認が
HTTP 400になった場合は必ず共有すること、期間再設計が必要になる)。
成功した場合は、3 split分の`trade_count`/`excess_return`/
`stock_by_stock_distribution`/`universe_resolution`の要約を共有して
もらえれば、Research Journal(`12_reports/experiment/`)への反映を
手伝える。**Locked Test結果はUnlock後に初めて見る想定のため、貼り付ける
前に「これは正式なEvidenceとして扱ってよいか(Train/Validationで既に
見えていた傾向の延長でしかないか)」を一度確認してから共有すること。**
