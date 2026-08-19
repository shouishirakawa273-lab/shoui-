"""Phase5 v1.1: H0001-R2 Real-Data Validation Experiment。

Phase5 v1(合成Fixtureによる Smoke Run、`scripts/phase5_v1_short_term_
reversal.py`、DECISIONS.md D0062/D0063)で完成したPipelineを、実際の
J-Quants Price + PIT Universeで実行するためのScript。

**このセッションは`api.jquants.com`への接続を組織Policyにより拒否されて
おり(`curl`でCONNECT自体が403)、かつAPIキーも設定されていないため、
このセッション自身はこのScriptを実行できない。** 実行はユーザー自身の
ローカルPC上で行う(`PHASE5_V1_LOCAL_VALIDATION_GUIDE.md`参照)。

## H0001を書き換えない(Phase5 v1.1要件§6)

Hypothesis(`H0001`、`04_hypotheses/H0001_2026-08-19_short_term_
reversal.md`)のClaim/Mechanism/Signal定義/Holding Periodは一切変更
しない。5営業日Trailing Return < 0 -> BUY、10営業日保有、という
Core Ruleをそのまま維持する。

## Preregistration Lineage(Phase5 v1.1要件§5、DECISIONS.md D0065)

Synthetic Preregistration(`PREREG0001`)を直接上書きせず、
`Preregistration.revise()`(既存のLineage機構、複製ではない)で
`PREREG0001_R2`を発行する。`parent_preregistration_id=PREREG0001`が
自動的に記録され、Registry上でLineageが明示される。変更するCore
Fieldsは実データ固有のもの(`dataset_contract_id`/`universe_
definition`/3期間/`benchmark`)のみで、`primary_metric`/
`parameters`(lookback_days/holding_period_days)/`alternative_
explanations`/`falsification_condition`/`forbidden_capabilities`は
Synthetic版から変更しない。

**`PREREG0001_R1`について**: 当初のReal-data replication期間
(Train 2015-2019/Validation 2020-2021/Locked Test 2025)は、
実際のLocal Coverage Checkの結果、現在の契約プラン下では取得不能
(HTTP 400、2021年以前を含むRequestで再現)と判明したため、
**一度もPreregistration Registryへ`preregister()`・記録されないまま
Design段階で放棄した**(`PREREG0001_R1`という識別子自体、Immutability
違反やSilent Overwriteは発生していない — 単に実行前に破棄された計画)。
この経緯はDECISIONS.md D0065に記録する。`PREREG0001_R2`はこの反省を
踏まえ、Local Coverage Checkで確認済みのデータ提供期間内で再設計した
ものである(詳細はD0065参照)。

## Result Inspection Cannot Precede Preregistration(Phase5 v1.1要件§11)

`step_coverage_check()`はRow数・日付Coverage・欠損Bar・Universe Count・
Corporate Action件数・Benchmark Coverageのみを報告し、`lib.strategies.
short_term_reversal`のSignal関数も`lib.backtest.engine.BacktestEngine`
のRun機構も一切呼び出さない(Strategy Returnの計算をしない)。この
Scriptは他Stepのために`lib.strategies`/`lib.backtest.engine`を
Module冒頭でImportしているため、Import自体の不在では保証されない
— 保証は`step_coverage_check()`の関数本体がこれらを一切呼ばないという
実装規律による(Reviewer確認対象)。

## Primary Question != Secondary Question(Phase5 v1.1要件§7)

このRoundのPrimary Research Questionは「Phase5 Validation Pipelineが
実際のJ-Quants Price + PIT Universeで正しく・再現可能に動作するか」
(Pipeline Validation)であり、「H0001が儲かるか」ではない。H0001が実データ
上でどう見えるかはSecondary Questionであり、Pipelineが正常動作したことを
もってH0001自体が支持されたと自動的に主張しない(この2つを混同しない)。
最終的な判断はConclusion Recordで両者を明示的に分けて記述する。

## Data Boundary

Price(Adjusted OHLCV) + PIT Universeのみ(D0061)。Fundamentals/
Disclosures/Positioning/Macro/Global Market/News/Consensus/Evidence
Pathは一切Importしない。

## 対象銘柄の既定値について(Pre-run skeptic-review LOW Finding対応、D0065で再確認)

`_parse_codes()`の既定値(7203/6758/8056/3626)は、RESEARCH_RULES.mdの
「燃え尽きた期間」記録(2022-01-04〜2024-12-30・同じ4銘柄・20営業日
Momentum→60営業日保有)と**銘柄が完全に一致し、かつ期間もほぼ完全に
重複する**(`PREREG0001_R2`のTrain/Validation期間は2022-01-04〜
2024-12-30、後述)。「燃え尽きた」の定義は期間・銘柄・Strategy
パラメータの組み合わせ全体であり、H0001のMechanism(5営業日Reversal・
10営業日保有)は燃え尽きた組み合わせ(20営業日Momentum・60営業日保有)
と異なるため、組み合わせとしては未観測のHidden Testのままであるが、
D0065時点でこの重複はデータ提供期間の制約上避けられない(利用可能な
実データが約4年分[2022年以降]しかなく、燃え尽きた期間[2022-2024]と
ほぼ同じ範囲しか残っていない)。この重複はConfirmation Biasの観点で
D0065のskeptic-reviewerに明示的に確認させた(結果は同Decisionを参照)。
4銘柄自体もUniverse選定として独立した根拠(流動性・時価総額等)を
持たないままであり、より広いPIT Universe(`lib.universe`)由来の
機械的な選定へ切り替える案はD0065で検討したが、このRoundでは
実施しない(Backlog、理由はD0065参照)。4銘柄は少数のため、Synthetic
Roundと同様にSignalが実質的に一部銘柄へ偏るRiskがある(Q節で必ず
Reportすること)。

## Real Benchmark(Phase5 v1.1要件§17-18)

`/v2/indices/bars/daily/topix`から取得する実TOPIX日次Indexを使う
(合成Benchmarkは使わない)。公式に公表された過去時点のIndex値は、
その時点で実際に採用されていた構成銘柄を反映して計算・確定済みの
値であり、現在の構成銘柄一覧を過去へ遡って適用するのと違い、
Look-ahead的な混入はない(公表済みIndex値そのものを時系列で取得
するだけであり、このLabがIndexを再構築するわけではない)。

使い方(D0065で再設計した期間。**--step preregisterの前に、必ず
以下のCoverage Check(特に2022-01-04〜2025-12-30を1回で要求する
マルチイヤーRequest)がHTTP 400にならないことを確認すること** —
`_load_real_price_data()`は`train_period_start`から各splitの
end_sessionまでを1リクエストで要求するため、Locked Test実行時には
Train開始日からLocked Test終了日までの全期間が単一Requestになる):
    python scripts/phase5_v1_1_h0001_real_data.py --step coverage-check \
        --codes 7203 6758 8056 3626 --start 2022-01-04 --end 2025-12-30
    python scripts/phase5_v1_1_h0001_real_data.py --step preregister \
        --codes 7203 6758 8056 3626 \
        --train-start 2022-01-04 --train-end 2023-12-29 \
        --validation-start 2024-01-04 --validation-end 2024-12-30 \
        --locked-test-start 2025-01-06 --locked-test-end 2025-12-30
    python scripts/phase5_v1_1_h0001_real_data.py --step train
    python scripts/phase5_v1_1_h0001_real_data.py --step validation
    python scripts/phase5_v1_1_h0001_real_data.py --step unlock-locked-test \
        --reason "..." --actor "..."
    python scripts/phase5_v1_1_h0001_real_data.py --step locked-test
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import asdict
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

_REPO_ROOT = Path(__file__).resolve().parent.parent
_LAB_DIR = _REPO_ROOT / "Japanese_Equity_Lab"
sys.path.insert(0, str(_LAB_DIR))

from lib.backtest.engine import DataSplit  # noqa: E402
from lib.backtest.price_history import AsOfAdjustedPriceHistory, PriceHistorySource  # noqa: E402
from lib.data_sources.convert import (  # noqa: E402
    detect_corporate_action_events_from_equity_bars,
    equities_master_payload_to_listing_records,
    equity_bars_payload_to_raw_bars,
    topix_bars_payload_to_raw_bars,
    trading_calendar_payload_to_calendar,
)
from lib.data_sources.jquants import JQuantsAdapter  # noqa: E402
from lib.errors import LockedTestAccessError, PreregistrationImmutabilityError  # noqa: E402
from lib.market_calendar import TradingCalendar, session_close_at  # noqa: E402
from lib.registry.experiment_registry import ExperimentRegistry  # noqa: E402
from lib.registry.provenance import ProvenanceLink, ProvenanceStore  # noqa: E402
from lib.reproducibility import current_code_commit, dataset_hash_from_snapshots, hash_json_safe, is_git_dirty  # noqa: E402
from lib.research.dataset_contract import DatasetContract  # noqa: E402
from lib.research.locked_test import AccessStage, FileBackedLockedTestGate  # noqa: E402
from lib.research.preregistration import Preregistration, PreregistrationStatus  # noqa: E402
from lib.research.registry import PreregistrationRegistry  # noqa: E402
from lib.research.runner import run_split  # noqa: E402
from lib.schemas.experiment import (  # noqa: E402
    Experiment,
    ExperimentStatus,
    PriceAdjustmentProvenance,
    ReproducibilityFingerprint,
)
from lib.schemas.price_data import apply_split_adjustments  # noqa: E402
from lib.snapshot import RawSnapshotStore, SnapshotManifest  # noqa: E402
from lib.strategies.short_term_reversal import (  # noqa: E402
    STRATEGY_ID,
    STRATEGY_VERSION,
    as_buy_signal_fn,
    config_from_preregistration_parameters,
)
from lib.universe import ListingBasedUniverseProvider  # noqa: E402

HYPOTHESIS_ID = "H0001"
PARENT_PREREGISTRATION_ID = "PREREG0001"
PREREGISTRATION_ID = "PREREG0001_R2"
DATASET_CONTRACT_ID = "DC0002_JQUANTS_REAL_V1"
EXPERIMENT_ID = "BT_PHASE5_V1_1_H0001_R2"

_PREREGISTRATION_REGISTRY_PATH = _LAB_DIR / "06_backtests" / "preregistrations.jsonl"
_LOCKED_TEST_AUDIT_PATH = _LAB_DIR / "06_backtests" / "locked_test_audit_real.jsonl"
_EXPERIMENT_REGISTRY_PATH = _LAB_DIR / "06_backtests" / "experiment_registry.jsonl"
_PROVENANCE_PATH = _LAB_DIR / "06_backtests" / "provenance.jsonl"

_SPLIT_LABEL = {DataSplit.TRAIN: "train_period", DataSplit.VALIDATION: "validation_period", DataSplit.TEST: "locked_test_period"}


def step_coverage_check(*, codes: tuple[str, ...], start: date, end: date, adapter: JQuantsAdapter | None = None) -> None:
    """Real Data Coverage Check(Phase5 v1.1要件§8)。Strategy Returnは一切計算しない。

    `adapter`はTest用の依存注入Point(既定はNoneで実際の`JQuantsAdapter()`を使う、
    `JQuantsAdapter(api_key=..., session=...)`が既に持つDI Patternと同じ)。
    """
    if adapter is None:
        adapter = JQuantsAdapter()
    quotes_result = adapter.fetch_equity_bars(codes=list(codes), start_date=start, end_date=end)
    calendar_result = adapter.fetch_trading_calendar(start_date=start, end_date=end)
    topix_result = adapter.fetch_topix_bars(start_date=start, end_date=end)
    master_result = adapter.fetch_equities_master()

    raw_bars = equity_bars_payload_to_raw_bars(quotes_result.payload, source="jquants")
    raw_by_code: dict[str, list] = {}
    for bar in raw_bars:
        raw_by_code.setdefault(bar.code, []).append(bar)

    print(f"=== Coverage Check: {start} 〜 {end} ===")
    print(f"requested codes: {codes}")
    calendar_dates = {row["Date"] for row in calendar_result.payload if row.get("HolDiv") == "1"}
    print(f"trading calendar sessions in range: {len(calendar_dates)}")

    for code in codes:
        bars = sorted(raw_by_code.get(code, []), key=lambda b: b.session_date)
        missing_open = sum(1 for b in bars if b.open is None)
        missing_close = sum(1 for b in bars if b.close is None)
        first = bars[0].session_date if bars else None
        last = bars[-1].session_date if bars else None
        print(
            f"  {code}: bar_count={len(bars)} first={first} last={last} missing_open={missing_open} missing_close={missing_close}"
        )

    events = detect_corporate_action_events_from_equity_bars(quotes_result.payload)
    events_by_code: dict[str, int] = {}
    for e in events:
        events_by_code[e.code] = events_by_code.get(e.code, 0) + 1
    print(f"corporate action events detected: {dict(events_by_code)}")

    topix_bars = topix_bars_payload_to_raw_bars(topix_result.payload, source="jquants")
    print(
        f"TOPIX bars: count={len(topix_bars)} first={topix_bars[0].session_date if topix_bars else None} "
        f"last={topix_bars[-1].session_date if topix_bars else None}"
    )

    listing_records = equities_master_payload_to_listing_records(master_result.payload)
    universe_provider = ListingBasedUniverseProvider(listing_records)
    from lib.market_calendar import session_close_at

    for probe_date in (start, end):
        snapshot = universe_provider.as_of(session_close_at(probe_date))
        eligible = [c for c in codes if c in snapshot.codes]
        print(f"PIT universe as_of={probe_date}: eligible among requested codes={eligible} (resolution={snapshot.resolution})")

    print(
        "\n上記はStructural Inspectionのみであり、Strategy Return/Signal件数は含まない"
        "(Phase5 v1.1要件§11、Result Inspection Cannot Precede Preregistration)。"
    )


def build_real_preregistration(
    *,
    codes: tuple[str, ...],
    train_start: date,
    train_end: date,
    validation_start: date,
    validation_end: date,
    locked_test_start: date,
    locked_test_end: date,
) -> Preregistration:
    parent_registry = PreregistrationRegistry(_PREREGISTRATION_REGISTRY_PATH)
    parent = parent_registry.get(PARENT_PREREGISTRATION_ID)
    if parent is None:
        raise SystemExit(f"親Preregistration {PARENT_PREREGISTRATION_ID} が見つかりません。Phase5 v1のRecordが必要です。")
    return parent.revise(
        new_preregistration_id=PREREGISTRATION_ID,
        research_question=parent.research_question + "(実データ、J-Quants Price + PIT Universe)",
        dataset_contract_id=DATASET_CONTRACT_ID,
        universe_definition=f"Price + PIT Universe(実データ)。対象銘柄: {','.join(codes)}",
        train_period_start=train_start,
        train_period_end=train_end,
        validation_period_start=validation_start,
        validation_period_end=validation_end,
        locked_test_period_start=locked_test_start,
        locked_test_period_end=locked_test_end,
        benchmark="TOPIX(実データ、/v2/indices/bars/daily/topix)",
    )


def step_preregister(
    *,
    codes: tuple[str, ...],
    train_start: date,
    train_end: date,
    validation_start: date,
    validation_end: date,
    locked_test_start: date,
    locked_test_end: date,
) -> None:
    registry = PreregistrationRegistry(_PREREGISTRATION_REGISTRY_PATH)
    if registry.get(PREREGISTRATION_ID) is not None:
        print(f"Preregistration {PREREGISTRATION_ID} は既に記録済みです(再登録しません)。")
        return
    preregistration = build_real_preregistration(
        codes=codes,
        train_start=train_start,
        train_end=train_end,
        validation_start=validation_start,
        validation_end=validation_end,
        locked_test_start=locked_test_start,
        locked_test_end=locked_test_end,
    ).preregister()
    registry.record(preregistration)
    print(
        f"Preregistration frozen and recorded: {preregistration.preregistration_id} "
        f"(parent={preregistration.parent_preregistration_id}, status={preregistration.status})"
    )


def build_dataset_contract(*, codes: tuple[str, ...], start: date, end: date) -> DatasetContract:
    return DatasetContract(
        dataset_contract_id=DATASET_CONTRACT_ID,
        source="J-Quants API V2(実データ、/v2/equities/bars/daily・/v2/markets/calendar・"
        "/v2/indices/bars/daily/topix・/v2/equities/master)",
        snapshot_reference=f"J-Quants real fetch, codes={','.join(codes)}, {start}〜{end}",
        date_range_start=start,
        date_range_end=end,
        universe_mechanism="lib.universe.ListingBasedUniverseProvider(実Equities Master由来のPIT Universe)",
        pit_mechanism="lib.point_in_time.PointInTimeRecord / lib.backtest.engine.BacktestEngineのdecision_at機構",
        adjustment_method="PIT_AS_OF_ADJFACTOR_V1(decision_atごとのAs-of Adjustment、D0034/D0035)",
        missing_handling="欠損はUNEXECUTABLE_NO_OPEN等として記録しfallbackしない(lib.backtest.engine既存方針)",
        corporate_action_handling="AdjFactor/ExRT由来のCorporate Action Eventを検出しPIT-safeに適用(Case B、Case Aは未実装)",
        delisting_handling=(
            "ListingBasedUniverseProviderは上場廃止銘柄も期間内はUniverseへ残す設計だが、"
            "これは実/v2/equities/masterの上場廃止Field(status等)の実際の値・網羅性に依存する"
            "(未確認・未検証)。Survivorship Bias防止は設計上の意図であり、実データでの保証ではない。"
            "実行結果のUniverseSnapshot.resolution/survivorship_bias_unresolvedを"
            "Experiment.notesで確認すること"
        ),
        liquidity_availability="既存BacktestEngineのPrice可用性判定のみ使用。新規Liquidity Signalは追加しない",
        feature_computation="5営業日Trailing Close-to-Close Return(lib.strategies.short_term_reversal)",
        target_computation="10営業日Holding、NEXT_SESSION_OPEN執行(lib.backtest.engine)",
        notes=(
            "Phase5 v1.1 Real-Data Validation Experiment(H0001-R2)。実データ実行はユーザーの"
            "ローカルPC上で行う。既知の限界: /v2/equities/masterはsplitごと(Train/Validation/"
            "Locked Test)に個別に取得しas_ofでPin留めしていないため、Real Masterデータが取得"
            "タイミング間で変化した場合、3 splitが厳密に同一のUniverse基盤を共有する保証はない。"
            "ただしこれはSnapshotManifest/dataset_hash_from_snapshotsで各split固有のRaw "
            "Snapshotとして記録されるため、サイレントな不整合ではない(再現性検証時に "
            "SnapshotのHashを比較すれば検出可能)。"
        ),
    )


def _load_real_price_data(
    *, codes: tuple[str, ...], split_label: str, data_start: date, data_end: date
) -> tuple[PriceHistorySource, list, TradingCalendar, ListingBasedUniverseProvider, list[SnapshotManifest]]:
    """`data_start`から`data_end`(=呼び出し元splitのend_session)までのみを取得する。

    Phase5 v1のSplit境界Bug(DECISIONS.md D0062)と同じ理由により、splitごとに
    個別にデータを取得し直す。
    """
    adapter = JQuantsAdapter()
    snapshot_store = RawSnapshotStore(_LAB_DIR / "01_data" / "raw")

    quotes_result = adapter.fetch_equity_bars(codes=list(codes), start_date=data_start, end_date=data_end)
    calendar_result = adapter.fetch_trading_calendar(start_date=data_start, end_date=data_end)
    topix_result = adapter.fetch_topix_bars(start_date=data_start, end_date=data_end)
    master_result = adapter.fetch_equities_master()

    raw_bars = equity_bars_payload_to_raw_bars(quotes_result.payload, source="jquants")
    raw_by_code: dict[str, list] = {}
    for bar in raw_bars:
        raw_by_code.setdefault(bar.code, []).append(bar)

    corporate_action_events = detect_corporate_action_events_from_equity_bars(quotes_result.payload)
    events_by_code: dict[str, list] = {code: [] for code in codes}
    for event in corporate_action_events:
        events_by_code.setdefault(event.code, []).append(event)
    price_history: PriceHistorySource = AsOfAdjustedPriceHistory(raw_by_code, events_by_code)

    benchmark_raw_bars = topix_bars_payload_to_raw_bars(topix_result.payload, source="jquants")
    benchmark_bars = apply_split_adjustments(benchmark_raw_bars, [])

    trading_calendar = trading_calendar_payload_to_calendar(calendar_result.payload, range_start=data_start, range_end=data_end)

    listing_records = equities_master_payload_to_listing_records(master_result.payload)
    universe_provider = ListingBasedUniverseProvider(listing_records)

    manifests = [
        snapshot_store.save(quotes_result, snapshot_id=f"SNAP_{EXPERIMENT_ID}_{split_label}_equity_bars"),
        snapshot_store.save(calendar_result, snapshot_id=f"SNAP_{EXPERIMENT_ID}_{split_label}_trading_calendar"),
        snapshot_store.save(topix_result, snapshot_id=f"SNAP_{EXPERIMENT_ID}_{split_label}_topix"),
        snapshot_store.save(master_result, snapshot_id=f"SNAP_{EXPERIMENT_ID}_{split_label}_equities_master"),
    ]
    return price_history, benchmark_bars, trading_calendar, universe_provider, manifests


def _load_preregistration() -> Preregistration:
    registry = PreregistrationRegistry(_PREREGISTRATION_REGISTRY_PATH)
    preregistration = registry.get(PREREGISTRATION_ID)
    if preregistration is None:
        raise SystemExit(f"Preregistration {PREREGISTRATION_ID} が見つかりません。先に --step preregister を実行してください。")
    if preregistration.status != PreregistrationStatus.PREREGISTERED:
        raise PreregistrationImmutabilityError(f"Preregistration {PREREGISTRATION_ID} はPREREGISTERED状態ではありません")
    preregistration.assert_not_mutated()
    return preregistration


def _run_and_record(
    split: DataSplit, *, codes: tuple[str, ...], locked_test_gate: FileBackedLockedTestGate | None = None
) -> None:
    preregistration = _load_preregistration()
    dataset_contract = build_dataset_contract(
        codes=codes, start=preregistration.train_period_start, end=preregistration.locked_test_period_end
    )
    strategy_config = config_from_preregistration_parameters(preregistration.parameters)

    period_field = _SPLIT_LABEL[split]
    data_end = getattr(preregistration, f"{period_field}_end")
    price_history, benchmark_bars, trading_calendar, universe_provider, manifests = _load_real_price_data(
        codes=codes, split_label=split.value, data_start=preregistration.train_period_start, data_end=data_end
    )

    result = run_split(
        preregistration=preregistration,
        dataset_contract_hash=dataset_contract.contract_hash(),
        split=split,
        universe_codes=codes,
        price_history=price_history,
        benchmark_bars=benchmark_bars,
        trading_calendar=trading_calendar,
        signal_fn=as_buy_signal_fn(strategy_config),
        universe_provider=universe_provider,
        locked_test_gate=locked_test_gate,
        experiment_id=EXPERIMENT_ID if split == DataSplit.TEST else None,
    )

    # Pre-run PIT Audit MEDIUM Finding対応: UniverseSnapshotのresolution/
    # survivorship_bias_unresolvedはBacktestEngine内部でdecision_dateごとに
    # 解決されるがExperiment Recordへは伝播しない(BacktestMetricsに該当Fieldが
    # 無いため)。このScript独自にsplit境界(開始・終了)でas_of()を呼び、
    # 少なくともこのExperiment Recordの`notes`へ残す(この一連の実行で
    # Survivorship Biasが未解決だったかどうかを、Metricsだけを見た将来の
    # 読者が見失わないようにする)。
    period_start = getattr(preregistration, f"{period_field}_start")

    universe_probe_notes = []
    for probe_date in (period_start, data_end):
        snapshot = universe_provider.as_of(session_close_at(probe_date))
        universe_probe_notes.append(f"{probe_date}:{snapshot.resolution.value}")
        if snapshot.survivorship_bias_unresolved:
            universe_probe_notes[-1] += ":survivorship_bias_unresolved"

    dataset_hash = dataset_hash_from_snapshots([m.content_hash for m in manifests])
    strategy_hash = hash_json_safe({"strategy_id": STRATEGY_ID, "version": STRATEGY_VERSION, "config": asdict(strategy_config)})
    config_hash = hash_json_safe({"split": split.value, "preregistration_id": PREREGISTRATION_ID})
    fingerprint = ReproducibilityFingerprint(
        run_id=f"RUN_{EXPERIMENT_ID}_{split.value}",
        dataset_hash=dataset_hash,
        strategy_hash=strategy_hash,
        config_hash=config_hash,
        code_commit=current_code_commit(cwd=str(_REPO_ROOT)),
        git_dirty=is_git_dirty(cwd=str(_REPO_ROOT)),
    )
    price_adjustment = PriceAdjustmentProvenance(
        adjustment_method="PIT_AS_OF_ADJFACTOR_V1",
        as_of_policy="decision_at",
        corporate_action_source="jquants_v2_adjfactor",
        raw_snapshot_ids=tuple(m.snapshot_id for m in manifests),
    )

    experiment = Experiment(
        experiment_id=f"{EXPERIMENT_ID}_{split.value}",
        hypothesis_id=HYPOTHESIS_ID,
        strategy_id=STRATEGY_ID,
        status=ExperimentStatus.TESTED,
        metrics=result.metrics,
        reproducibility=fingerprint,
        price_adjustment=price_adjustment,
        notes=(
            f"Phase5 v1.1 Real-Data Validation Experiment(H0001-R2)、split={split.value}、"
            f"universe_resolution=[{','.join(universe_probe_notes)}]"
        ),
        preregistration_id=result.preregistration_id,
        dataset_contract_hash=result.dataset_contract_hash,
    )
    exp_registry = ExperimentRegistry(_EXPERIMENT_REGISTRY_PATH)
    exp_registry.record(experiment)

    provenance = ProvenanceStore(_PROVENANCE_PATH)
    provenance.add_link(
        ProvenanceLink(
            link_id=f"L_{experiment.experiment_id}_1",
            from_type="hypothesis",
            from_id=HYPOTHESIS_ID,
            to_type="experiment",
            to_id=experiment.experiment_id,
        )
    )

    print(f"=== split={split.value} experiment_id={experiment.experiment_id} ===")
    print(f"trade_count={result.metrics.trade_count} signal_count={result.metrics.signal_count}")
    print(f"excess_return={result.metrics.excess_return} benchmark_return={result.metrics.benchmark_return}")
    print(f"stock_by_stock_distribution keys={list(result.metrics.stock_by_stock_distribution.keys())}")


def step_unlock_locked_test(*, reason: str, actor: str) -> None:
    gate = FileBackedLockedTestGate(_LOCKED_TEST_AUDIT_PATH)
    record = gate.unlock(experiment_id=EXPERIMENT_ID, reason=reason, actor=actor)
    print(f"Locked Test unlocked: experiment_id={record.experiment_id} actor={record.actor} at={record.unlocked_at.isoformat()}")
    print(f"AccessStage: {AccessStage.LOCKED_TEST.value}")


def _parse_codes(raw: list[str] | None) -> tuple[str, ...]:
    return tuple(raw) if raw else ("7203", "6758", "8056", "3626")


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--step",
        required=True,
        choices=["coverage-check", "preregister", "train", "validation", "unlock-locked-test", "locked-test"],
    )
    parser.add_argument("--codes", nargs="+", default=None)
    parser.add_argument("--start", type=date.fromisoformat, default=None)
    parser.add_argument("--end", type=date.fromisoformat, default=None)
    parser.add_argument("--train-start", type=date.fromisoformat, default=None)
    parser.add_argument("--train-end", type=date.fromisoformat, default=None)
    parser.add_argument("--validation-start", type=date.fromisoformat, default=None)
    parser.add_argument("--validation-end", type=date.fromisoformat, default=None)
    parser.add_argument("--locked-test-start", type=date.fromisoformat, default=None)
    parser.add_argument("--locked-test-end", type=date.fromisoformat, default=None)
    parser.add_argument("--reason", default="")
    parser.add_argument("--actor", default="")
    args = parser.parse_args()

    codes = _parse_codes(args.codes)

    if args.step == "coverage-check":
        if args.start is None or args.end is None:
            raise SystemExit("--step coverage-check には --start と --end が必須です")
        step_coverage_check(codes=codes, start=args.start, end=args.end)
    elif args.step == "preregister":
        required = [
            args.train_start,
            args.train_end,
            args.validation_start,
            args.validation_end,
            args.locked_test_start,
            args.locked_test_end,
        ]
        if any(v is None for v in required):
            raise SystemExit(
                "--step preregister には --train-start/--train-end/--validation-start/"
                "--validation-end/--locked-test-start/--locked-test-end が全て必須です"
            )
        step_preregister(
            codes=codes,
            train_start=args.train_start,
            train_end=args.train_end,
            validation_start=args.validation_start,
            validation_end=args.validation_end,
            locked_test_start=args.locked_test_start,
            locked_test_end=args.locked_test_end,
        )
    elif args.step == "train":
        _run_and_record(DataSplit.TRAIN, codes=codes)
    elif args.step == "validation":
        _run_and_record(DataSplit.VALIDATION, codes=codes)
    elif args.step == "unlock-locked-test":
        if not args.reason or not args.actor:
            raise SystemExit("--step unlock-locked-test には --reason と --actor の両方が必須です")
        step_unlock_locked_test(reason=args.reason, actor=args.actor)
    elif args.step == "locked-test":
        gate = FileBackedLockedTestGate(_LOCKED_TEST_AUDIT_PATH)
        try:
            _run_and_record(DataSplit.TEST, codes=codes, locked_test_gate=gate)
        except LockedTestAccessError as exc:
            raise SystemExit(f"Locked Testを実行できません: {exc}\n先に --step unlock-locked-test を実行してください。") from exc


if __name__ == "__main__":
    main()
