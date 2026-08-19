# PHASE5_V1_LOCAL_VALIDATION_GUIDE.md — H0001の実データLocked Test実行手順

## なぜこの手順が必要か

このセッションはJ-Quants公式APIへ接続できない(EGRESS_BLOCKED、
`DECISIONS.md`複数箇所参照)。そのため`scripts/phase5_v1_short_term_
reversal.py`で実行した一連のTrain/Validation/Locked Testは、合成
Fixtureデータ(`13_tests/fixtures/synthetic_jquants_v2_bars.json`)
による**Smoke Run(Pipeline配線・Infrastructure Validation)であり、
投資判断のEvidenceではない**(`12_reports/experiment/BT_PHASE5_V1_
H0001_SMOKE_V2_2026-08-19_report.md`参照)。H0001(Short-term
Reversal)を実データで検証するには、ネットワーク接続可能なあなたの
ローカル環境で以下を実行する必要がある。

**重要**: `scripts/phase5_v1_short_term_reversal.py`は現状Fixture
専用に固定されている(このセッションが実APIを検証できないため)。
実データ実行には、後述の**新しいPreregistration**(既存
`PREREG0001`とは別ID、`dataset_contract_id`が異なる=異なるDataset
Contractのため)を発行する小さなAdaptationが必要。Hypothesis
(`H0001`)自体・Signal定義・パラメータ(`lookback_days=5`/
`holding_period_days=10`)は変更しない。

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
GUIDE.md`手順1-2と同じ)。

## C. 小さなSmoke Test(1銘柄・数日)

```powershell
cd shoui-
python -c "
from dotenv import load_dotenv
load_dotenv()
import sys
sys.path.insert(0, 'Japanese_Equity_Lab')
from datetime import date
from lib.data_sources.jquants import JQuantsAdapter
adapter = JQuantsAdapter()
result = adapter.fetch_equity_bars(codes=['7203'], start_date=date(2024,1,4), end_date=date(2024,1,10))
print(result.payload[:2])
"
```

## D. 対象期間・銘柄の選定(RESEARCH_RULES.mdの制約を守る)

`RESEARCH_RULES.md`の「燃え尽きた期間」記録により、**2022-01-04〜
2024-12-30・銘柄7203/6758/8056/3626・固定Strategy(20営業日Momentum→
60営業日保有)の組み合わせは、既に結果を観測済みのため「未見のHidden
Test」として再利用できない。** H0001は別Mechanism(Reversal・
5営業日/10営業日)だが、疑わしきは避ける観点から、対象銘柄
またはTrain/Validation/Locked Test期間の少なくとも一方をこの組み合わせ
とは変えることを推奨する(例: 銘柄はそのまま7203/6758/8056/3626でも、
期間を2015-2019/2020-2021/2025のように上記期間の外へ設定する)。

以下は一例(調整して構わないが、**一度Preregistrationを`preregister()`
したら書き換えない**こと。書き換えたくなったら新しい`preregistration_id`
で`revise()`する)。

- Train: 2015-01-05 〜 2019-12-30
- Validation: 2020-01-06 〜 2021-12-30
- Locked Test: 2025-01-06 〜 2025-12-30

## E. 新しいPreregistrationを構築する(実データ用、既存PREREG0001とは別ID)

`scripts/phase5_v1_short_term_reversal.py`の`build_preregistration()`
を参考に、以下のようなPythonスニペットをローカルで実行する
(このLabの`lib.research`をそのまま再利用、新規実装は不要)。

```python
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, "Japanese_Equity_Lab")
from lib.research.preregistration import Preregistration
from lib.research.registry import PreregistrationRegistry

research_question = "短期(5営業日)Trailing Returnが負の銘柄は、その後TOPIX対比で超過リターンを生むか(実データ)"
falsification_condition = "Locked Test期間でexcess_returnが0以下であれば、この仮説は支持されない"
universe_definition = "Price + PIT Universeのみ(Phase5 v1要件§5)。対象銘柄はDに従って選定"

preregistration = Preregistration(
    preregistration_id="PREREG0002_REAL",
    hypothesis_id="H0001",
    research_question=research_question,
    alternative_explanations=(
        "単なる取引コスト以下のノイズである可能性",
        "特定の対象期間・対象銘柄への依存であり、市場全体には一般化できない可能性",
    ),
    falsification_condition=falsification_condition,
    dataset_contract_id="DC0002_JQUANTS_REAL_V1",  # 実データ用の新しいDataset Contract ID
    universe_definition=universe_definition,
    train_period_start=date(2015, 1, 5),
    train_period_end=date(2019, 12, 30),
    validation_period_start=date(2020, 1, 6),
    validation_period_end=date(2021, 12, 30),
    locked_test_period_start=date(2025, 1, 6),
    locked_test_period_end=date(2025, 12, 30),
    primary_metric="excess_return",
    benchmark="TOPIX",
    parameters=(("lookback_days", "5"), ("holding_period_days", "10")),
).preregister()

registry_path = Path("Japanese_Equity_Lab/06_backtests/preregistrations.jsonl")
PreregistrationRegistry(registry_path).record(preregistration)
print("preregistered:", preregistration.preregistration_id, preregistration.status)
```

**この時点でPreregistrationは固定される。Locked Test結果を見るまでは
この内容を変更しないこと。**

## F. Train/Validation/Locked Testを実データで実行する

`scripts/phase5_v1_short_term_reversal.py`は`FixtureDataSourceAdapter`
専用のため、実データ実行には`_build_experiment_runner`相当の処理を
`JQuantsAdapter`ベースに差し替えたローカル用スクリプトが必要。
既存の`scripts/jquants_lab_pipeline.py`(`--source jquants`)が
実データ取得・Raw Snapshot保存・PIT-safe Adjustment適用の全ての配線
を持っているため、そのDataソース部分(`_build_adapter`〜
`trading_calendar`構築まで)をコピーし、`lib.research.runner.
run_split()`へ渡す形に組み替えるのが最短経路。`lib.research.runner`
自体はSource非依存(`PriceHistorySource`/`TradingCalendar`/
`Sequence[AdjustedOHLCVBar]`というInterfaceのみに依存)なので、
`lib/research/`側の変更は一切不要。

各splitについて、**必ずそのsplit自身の`end_session`までのデータのみ**
を渡すこと(`run_split()`は`SplitBoundaryLeakageError`でこれを検証
するため、越えていれば実行時に即座に失敗する — DECISIONS.md D0062
参照)。

```python
from lib.backtest.engine import DataSplit
from lib.research.runner import run_split
# price_history / benchmark_bars / trading_calendar は
# scripts/jquants_lab_pipeline.py の該当部分を参考に、
# 各splitのend_sessionまでで構築する。

result = run_split(
    preregistration=preregistration,
    dataset_contract_hash=dataset_contract.contract_hash(),
    split=DataSplit.TRAIN,  # 次にVALIDATION
    universe_codes=("7203", "6758", "8056", "3626"),
    price_history=price_history,
    benchmark_bars=benchmark_bars,
    trading_calendar=trading_calendar,
    signal_fn=as_buy_signal_fn(ShortTermReversalConfig(lookback_days=5, holding_period_days=10)),
)
print(result.metrics.trade_count, result.metrics.excess_return)
```

## G. Locked Testを一度だけUnlockして実行する

Train/Validationの結果を確認し、`allowed_adjustments`(Transaction
Cost前提のみ)以外は一切変更しないと決めたら:

```python
from lib.research.locked_test import FileBackedLockedTestGate
from pathlib import Path

gate = FileBackedLockedTestGate(Path("Japanese_Equity_Lab/06_backtests/locked_test_audit_real.jsonl"))
gate.unlock(experiment_id="BT_PHASE5_V1_H0001_REAL", reason="Train/Validation完了、Final Review実施", actor="<あなたの名前>")

result = run_split(
    preregistration=preregistration,
    dataset_contract_hash=dataset_contract.contract_hash(),
    split=DataSplit.TEST,
    ...,
    locked_test_gate=gate,
    experiment_id="BT_PHASE5_V1_H0001_REAL",
)
```

`gate.unlock()`は同じ`experiment_id`に対して二度目を呼ぶと
`LockedTestAccessError`になる(意図的、Knowledge Contamination防止)。

## H. 期待される観測(Falsifiable Checklist)

- Train/Validation/Locked Testそれぞれで`trade_count`>0(0ならUniverse
  ・期間・Signal定義を再確認、パラメータは変更しない)。
- 3 splitとも`stock_by_stock_distribution`が複数銘柄にまたがっている
  こと(Smoke Runでは単一銘柄[9984]のみだった限界が実データでは解消
  されているはず、`12_reports/experiment/`のSmoke Run Reportと比較)。
- `censored_count`が各splitのHolding Period・データ密度に応じて妥当な
  範囲であること(0のままなら境界処理を疑う)。
- Locked Test実行時に`SplitBoundaryLeakageError`/`LockedTestAccessError`
  が出ないこと(出たらG節の手順を再確認)。

## I. Claudeへ貼り戻す内容

エラーが出た場合は、エラーメッセージ全文(**APIキーの値を除いて**)を
貼り付けてもらえれば対応できる。成功した場合は、3 split分の
`trade_count`/`excess_return`/`stock_by_stock_distribution`の要約を
共有してもらえれば、Research Journal(`12_reports/experiment/`)への
反映を手伝える。**Locked Test結果はUnlock後に初めて見る想定のため、
貼り付ける前に「これは正式なEvidenceとして扱ってよいか(Train/
Validationで既に見えていた傾向の延長でしかないか)」を一度確認して
から共有すること。**
