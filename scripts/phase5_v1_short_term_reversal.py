"""Phase5 v1 First Hypothesis(H0001: Short-term Reversal)実行Script。

Preregistration(不変)-> Dataset Contract -> Train/Validation/Locked Test
という、`lib/research/`(Preregistration/DatasetContract/LockedTestGate/
PreregistrationRegistry/runner)を実際に動かす唯一のEntry Pointである。
Backtest Engine自体は新規実装せず`lib.backtest.engine.BacktestEngine`を
そのまま使い、`scripts/jquants_lab_pipeline.py`と同じデータ変換関数
(`lib.data_sources.convert`)・Raw Snapshot保存(`lib.snapshot.
RawSnapshotStore`)・Experiment記録(`lib.registry.experiment_registry.
ExperimentRegistry`)を再利用する。

**このScriptで使えるDataはPrice(Adjusted OHLCV)のみ**(D0061 Phase5 v1
Forbidden Data、`lib.research.preregistration.DEFAULT_FORBIDDEN_
CAPABILITIES`)。Fundamentals/Positioning/News/Macro/Consensus等は
一切Importしない。

現在このセッションはJ-Quants公式APIへ接続できないため(EGRESS_BLOCKED)、
このScriptが生成する結果は`--source fixture`(合成データ)によるSmoke Run
専用であり、**投資判断のEvidenceとして扱ってはならない**。実データでの
Locked Test実行は`PHASE5_V1_LOCAL_VALIDATION_GUIDE.md`を参照し、
ユーザー自身のPCで実行すること。

使い方:
    python scripts/phase5_v1_short_term_reversal.py --step preregister
    python scripts/phase5_v1_short_term_reversal.py --step train
    python scripts/phase5_v1_short_term_reversal.py --step validation
    python scripts/phase5_v1_short_term_reversal.py --step unlock-locked-test \
        --reason "Train/Validation完了、Final Review準備" --actor researcher
    python scripts/phase5_v1_short_term_reversal.py --step locked-test
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import asdict
from datetime import date
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_LAB_DIR = _REPO_ROOT / "Japanese_Equity_Lab"
sys.path.insert(0, str(_LAB_DIR))

from lib.backtest.engine import DataSplit  # noqa: E402
from lib.backtest.price_history import PriceHistorySource, StaticPriceHistory  # noqa: E402
from lib.data_sources.convert import equity_bars_payload_to_raw_bars, trading_calendar_payload_to_calendar  # noqa: E402
from lib.data_sources.fixture import FixtureDataSourceAdapter  # noqa: E402
from lib.errors import LockedTestAccessError, PreregistrationImmutabilityError  # noqa: E402
from lib.market_calendar import TradingCalendar  # noqa: E402
from lib.registry.experiment_registry import ExperimentRegistry  # noqa: E402
from lib.registry.provenance import ProvenanceLink, ProvenanceStore  # noqa: E402
from lib.reproducibility import (  # noqa: E402
    current_code_commit,
    dataset_hash_from_snapshots,
    hash_json_safe,
    is_git_dirty,
    source_code_state_hash,
)
from lib.research.dataset_contract import DatasetContract  # noqa: E402
from lib.research.locked_test import AccessStage, FileBackedLockedTestGate  # noqa: E402
from lib.research.preregistration import Preregistration, PreregistrationStatus  # noqa: E402
from lib.research.registry import PreregistrationRegistry  # noqa: E402
from lib.research.runner import run_split  # noqa: E402
from lib.schemas.experiment import Experiment, ExperimentStatus, ReproducibilityFingerprint  # noqa: E402
from lib.schemas.hypothesis import Hypothesis  # noqa: E402
from lib.schemas.price_data import apply_split_adjustments  # noqa: E402
from lib.snapshot import RawSnapshotStore, SnapshotManifest  # noqa: E402
from lib.strategies.short_term_reversal import (  # noqa: E402
    STRATEGY_ID,
    STRATEGY_VERSION,
    ShortTermReversalConfig,
    as_buy_signal_fn,
    config_from_preregistration_parameters,
)

FIXTURE_PATH = _LAB_DIR / "13_tests" / "fixtures" / "synthetic_jquants_v2_bars.json"
CODES = ("7203", "6758", "9984")
BENCHMARK_CODE = "TOPIX_SYNTH"

HYPOTHESIS_ID = "H0001"
PREREGISTRATION_ID = "PREREG0001"
DATASET_CONTRACT_ID = "DC0001_SMOKE_FIXTURE_V1"
# V2: BT_PHASE5_V1_H0001_SMOKE(無印)はPre-run PIT Audit(2026-08-19)でsplit境界を
# 越えたPrice参照Bug(_load_fixture_price_dataが常に全期間を取得していた)が確認され
# 無効化された(DECISIONS.md D0062参照)。Registryはappend-onlyのため無印のRecordは
# 削除せず残し、修正後の正式ChainはこのV2 IDで記録する。
EXPERIMENT_ID = "BT_PHASE5_V1_H0001_SMOKE_V2"

# 128営業日のFixture(2026-01-05〜2026-07-03)を厳密に時系列3分割する
# (Random Split禁止、Phase5 v1要件§19)。境界の選定はFixtureの実際の
# 取引日付から行った(合成データの構造上の都合であり、Signal閾値の
# 後付け調整ではない)。
TRAIN_START, TRAIN_END = date(2026, 1, 5), date(2026, 3, 4)
VALIDATION_START, VALIDATION_END = date(2026, 3, 5), date(2026, 5, 1)
LOCKED_TEST_START, LOCKED_TEST_END = date(2026, 5, 5), date(2026, 7, 3)

# 各splitのデータ取得は必ずこのsplit自身のend_sessionで打ち切る(TRAIN_START〜
# split自身のend_sessionまで、それより先は絶対に含めない)。lib.backtest.engine.
# BacktestEngineのRight Censoring(D0037)はtrading_calendar.range_end(通常
# config.end_sessionと一致)を境界として機能する — 3分割共通の全期間Calendar/
# PriceHistoryを使い回すと、この境界がsplitのend_sessionより先(Fixtureの最終日)
# まで伸びてしまい、TrainやValidationのTradeがsplit境界を越えて後続split(最悪
# Locked Test期間)のPriceで決済されてしまう(Pre-run PIT Audit BLOCKER、
# 2026-08-19)。必ずsplitごとに個別にデータを取得し直す。
_SPLIT_DATA_END: dict[DataSplit, date] = {
    DataSplit.TRAIN: TRAIN_END,
    DataSplit.VALIDATION: VALIDATION_END,
    DataSplit.TEST: LOCKED_TEST_END,
}

_PREREGISTRATION_REGISTRY_PATH = _LAB_DIR / "06_backtests" / "preregistrations.jsonl"
_LOCKED_TEST_AUDIT_PATH = _LAB_DIR / "06_backtests" / "locked_test_audit.jsonl"
_EXPERIMENT_REGISTRY_PATH = _LAB_DIR / "06_backtests" / "experiment_registry.jsonl"
_PROVENANCE_PATH = _LAB_DIR / "06_backtests" / "provenance.jsonl"


def build_hypothesis() -> Hypothesis:
    """H0001(04_hypotheses/H0001_2026-08-19_short_term_reversal.md参照)をLOCKする。"""
    return Hypothesis(
        hypothesis_id=HYPOTHESIS_ID,
        source_idea_id=None,
        claim="直近5営業日Trailing Close-to-Close Returnが負の銘柄は、その後平均的にTOPIX対比で超過リターンを生む(短期Reversal)",
        mechanism=(
            "短期的な過剰反応(overreaction)の反転。Panic Selling・ポジション調整による一時的な価格圧力が数営業日で解消される"
        ),
        universe="Phase5 v1要件によりPrice + PIT Universeのみ(東証PIT Universe)",
        signal_definition="直近5営業日Trailing Close-to-Close Returnが負",
        entry_rule="シグナル発生の翌営業日始値で買い(NEXT_SESSION_OPEN)",
        exit_rule="10営業日後の始値で手仕舞い",
        holding_period="10営業日",
        success_metric="TOPIX比 excess_return > 0 (Locked Test期間)",
        failure_metric="TOPIX比 excess_return <= 0 (Locked Test期間)",
        required_data=("J-Quants Price (Adjusted OHLCV)", "PIT Universe"),
    ).lock()


def build_preregistration() -> Preregistration:
    """H0001のPreregistration(DRAFT)。呼び出し側で`.preregister()`して固定する。"""
    return Preregistration(
        preregistration_id=PREREGISTRATION_ID,
        hypothesis_id=HYPOTHESIS_ID,
        research_question="短期(5営業日)Trailing Returnが負の銘柄は、その後TOPIX対比で超過リターンを生むか",
        alternative_explanations=(
            "単なる取引コスト以下のノイズである可能性(平均回帰は統計的ノイズでも頻繁に観測されうる)",
            "特定の対象期間・対象銘柄への依存であり、市場全体には一般化できない可能性(Overfitting/Sample-specific effect)",
        ),
        falsification_condition="Locked Test期間でexcess_returnが0以下であれば、この仮説は支持されない",
        dataset_contract_id=DATASET_CONTRACT_ID,
        universe_definition=(
            "Price + PIT Universeのみ(Phase5 v1要件§5)。このSmoke Runは合成Fixtureの固定3銘柄(7203/6758/9984)を使う"
        ),
        train_period_start=TRAIN_START,
        train_period_end=TRAIN_END,
        validation_period_start=VALIDATION_START,
        validation_period_end=VALIDATION_END,
        locked_test_period_start=LOCKED_TEST_START,
        locked_test_period_end=LOCKED_TEST_END,
        primary_metric="excess_return",
        secondary_metrics=("average_return", "win_rate", "max_drawdown", "trade_count", "sharpe相当は本Roundでは計算しない"),
        benchmark="TOPIX_SYNTH(Smoke Run合成Benchmark。実データ実行ではTOPIX)",
        parameters=(
            ("lookback_days", str(ShortTermReversalConfig().lookback_days)),
            ("holding_period_days", str(ShortTermReversalConfig().holding_period_days)),
        ),
        allowed_adjustments=(
            "Train/Validation結果を見た上でのTransaction Cost前提(commission_bps/slippage_bps)の変更のみ許可する"
            "(Signal定義・Threshold・Holding Period・Universe・Benchmark・Metricの変更は不許可、Phase5 v1要件§51)",
        ),
    )


def build_dataset_contract() -> DatasetContract:
    return DatasetContract(
        dataset_contract_id=DATASET_CONTRACT_ID,
        source="Fixture(合成データ、13_tests/fixtures/synthetic_jquants_v2_bars.json)。実データではない",
        snapshot_reference="synthetic_jquants_v2_bars.json (2026-01-05〜2026-07-03、7203/6758/9984/TOPIX_SYNTH)",
        date_range_start=TRAIN_START,
        date_range_end=LOCKED_TEST_END,
        universe_mechanism=(
            "固定3銘柄(7203/6758/9984)。PIT Universe(lib.universe)はこのSmoke Runでは未接続(Fixtureに上場/廃止情報が無いため)"
        ),
        pit_mechanism="lib.point_in_time.PointInTimeRecord / lib.backtest.engine.BacktestEngineのdecision_at機構",
        adjustment_method="NONE(FixtureのAdjFactorは全て1.0、調整不要)",
        missing_handling="欠損はUNEXECUTABLE_NO_OPEN等として記録しfallbackしない(lib.backtest.engine既存方針)",
        corporate_action_handling="このFixtureにはCorporate Action Eventが無い(AdjFactor=1.0固定)",
        delisting_handling="このSmoke Runでは対象外(Universe未接続、Local Validation Guideで実データ実行時に対応)",
        liquidity_availability="Fixtureのため流動性フィルタなし",
        feature_computation="5営業日Trailing Close-to-Close Return(lib.strategies.short_term_reversal)",
        target_computation="10営業日Holding、NEXT_SESSION_OPEN執行(lib.backtest.engine)",
        notes="Smoke Run専用。投資判断のEvidenceとして使用してはならない。",
    )


def _load_fixture_price_data(
    split_label: str, data_end: date
) -> tuple[PriceHistorySource, list, TradingCalendar, list[SnapshotManifest]]:
    """`TRAIN_START`から`data_end`(=呼び出し元splitのend_session)までのみを取得する。

    `data_end`より先のデータは一切取得しない。これによりtrading_calendarの
    range_endがsplit自身のend_sessionと一致し、BacktestEngineのRight Censoring
    (D0037)がsplit境界で正しく機能する(split境界を越えたExit Priceの参照を
    構造的に防ぐ、Pre-run PIT Audit BLOCKER修正)。
    """
    adapter = FixtureDataSourceAdapter(FIXTURE_PATH)
    snapshot_store = RawSnapshotStore(_LAB_DIR / "01_data" / "raw")

    quotes_result = adapter.fetch_equity_bars(codes=list(CODES), start_date=TRAIN_START, end_date=data_end)
    calendar_result = adapter.fetch_trading_calendar(start_date=TRAIN_START, end_date=data_end)
    benchmark_result = adapter.fetch_equity_bars(codes=[BENCHMARK_CODE], start_date=TRAIN_START, end_date=data_end)

    raw_bars = equity_bars_payload_to_raw_bars(quotes_result.payload, source="fixture")
    raw_by_code: dict[str, list] = {}
    for bar in raw_bars:
        raw_by_code.setdefault(bar.code, []).append(bar)
    price_history = StaticPriceHistory({code: apply_split_adjustments(bars, []) for code, bars in raw_by_code.items()})

    benchmark_raw_bars = equity_bars_payload_to_raw_bars(benchmark_result.payload, source="fixture")
    benchmark_bars = apply_split_adjustments(benchmark_raw_bars, [])

    trading_calendar = trading_calendar_payload_to_calendar(calendar_result.payload, range_start=TRAIN_START, range_end=data_end)

    manifests = [
        snapshot_store.save(quotes_result, snapshot_id=f"SNAP_{EXPERIMENT_ID}_{split_label}_equity_bars"),
        snapshot_store.save(calendar_result, snapshot_id=f"SNAP_{EXPERIMENT_ID}_{split_label}_trading_calendar"),
        snapshot_store.save(benchmark_result, snapshot_id=f"SNAP_{EXPERIMENT_ID}_{split_label}_benchmark"),
    ]
    return price_history, benchmark_bars, trading_calendar, manifests


def step_preregister() -> None:
    hypothesis = build_hypothesis()
    terms_hash_preview = (hypothesis.locked_terms_hash or "")[:16]
    print(f"Hypothesis locked: {hypothesis.hypothesis_id} (locked_terms_hash={terms_hash_preview}...)")

    registry = PreregistrationRegistry(_PREREGISTRATION_REGISTRY_PATH)
    if registry.get(PREREGISTRATION_ID) is not None:
        print(f"Preregistration {PREREGISTRATION_ID} は既に記録済みです(再登録しません)。")
        return
    preregistration = build_preregistration().preregister()
    registry.record(preregistration)
    print(f"Preregistration frozen and recorded: {preregistration.preregistration_id} (status={preregistration.status})")
    print(
        f"  train={TRAIN_START}〜{TRAIN_END} validation={VALIDATION_START}〜{VALIDATION_END} "
        f"locked_test={LOCKED_TEST_START}〜{LOCKED_TEST_END}"
    )


def _load_preregistration() -> Preregistration:
    registry = PreregistrationRegistry(_PREREGISTRATION_REGISTRY_PATH)
    preregistration = registry.get(PREREGISTRATION_ID)
    if preregistration is None:
        raise SystemExit(f"Preregistration {PREREGISTRATION_ID} が見つかりません。先に --step preregister を実行してください。")
    if preregistration.status != PreregistrationStatus.PREREGISTERED:
        raise PreregistrationImmutabilityError(f"Preregistration {PREREGISTRATION_ID} はPREREGISTERED状態ではありません")
    preregistration.assert_not_mutated()
    return preregistration


def _run_and_record(split: DataSplit, *, locked_test_gate: FileBackedLockedTestGate | None = None) -> None:
    preregistration = _load_preregistration()
    dataset_contract = build_dataset_contract()
    strategy_config = config_from_preregistration_parameters(preregistration.parameters)
    price_history, benchmark_bars, trading_calendar, manifests = _load_fixture_price_data(split.value, _SPLIT_DATA_END[split])

    result = run_split(
        preregistration=preregistration,
        dataset_contract_hash=dataset_contract.contract_hash(),
        split=split,
        universe_codes=CODES,
        price_history=price_history,
        benchmark_bars=benchmark_bars,
        trading_calendar=trading_calendar,
        signal_fn=as_buy_signal_fn(strategy_config),
        locked_test_gate=locked_test_gate,
        experiment_id=EXPERIMENT_ID if split == DataSplit.TEST else None,
    )

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
        source_code_state_hash=source_code_state_hash([_LAB_DIR / "lib", Path(__file__)], repo_root=_REPO_ROOT),
    )

    experiment = Experiment(
        experiment_id=f"{EXPERIMENT_ID}_{split.value}",
        hypothesis_id=HYPOTHESIS_ID,
        strategy_id=STRATEGY_ID,
        status=ExperimentStatus.TESTED,
        metrics=result.metrics,
        reproducibility=fingerprint,
        notes=f"Phase5 v1 Smoke Run(Fixture合成データ、投資判断のEvidenceではない)、split={split.value}",
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
    print(f"max_drawdown={result.metrics.max_drawdown} win_rate={result.metrics.win_rate}")


def step_unlock_locked_test(*, reason: str, actor: str) -> None:
    gate = FileBackedLockedTestGate(_LOCKED_TEST_AUDIT_PATH)
    record = gate.unlock(experiment_id=EXPERIMENT_ID, reason=reason, actor=actor)
    print(f"Locked Test unlocked: experiment_id={record.experiment_id} actor={record.actor} at={record.unlocked_at.isoformat()}")
    print(f"AccessStage: {AccessStage.LOCKED_TEST.value}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--step",
        required=True,
        choices=["preregister", "train", "validation", "unlock-locked-test", "locked-test"],
    )
    parser.add_argument("--reason", default="", help="--step unlock-locked-test 用のUnlock理由")
    parser.add_argument("--actor", default="", help="--step unlock-locked-test 用の実行者名")
    args = parser.parse_args()

    if args.step == "preregister":
        step_preregister()
    elif args.step == "train":
        _run_and_record(DataSplit.TRAIN)
    elif args.step == "validation":
        _run_and_record(DataSplit.VALIDATION)
    elif args.step == "unlock-locked-test":
        if not args.reason or not args.actor:
            raise SystemExit("--step unlock-locked-test には --reason と --actor の両方が必須です")
        step_unlock_locked_test(reason=args.reason, actor=args.actor)
    elif args.step == "locked-test":
        gate = FileBackedLockedTestGate(_LOCKED_TEST_AUDIT_PATH)
        try:
            _run_and_record(DataSplit.TEST, locked_test_gate=gate)
        except LockedTestAccessError as exc:
            raise SystemExit(f"Locked Testを実行できません: {exc}\n先に --step unlock-locked-test を実行してください。") from exc


if __name__ == "__main__":
    main()
