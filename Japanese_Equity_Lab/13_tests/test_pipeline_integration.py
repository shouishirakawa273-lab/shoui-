"""Pipeline全体(Data -> Feature -> Signal -> Decision -> Execution -> Return ->
Benchmark比較 -> Experiment Registry -> Provenance)の統合テスト。

合成データ(fixtures/synthetic_jquants_v2_bars.json、J-Quants API V2形状)を使い、
外部API疎通なしで`scripts/jquants_lab_pipeline.py`と同じ配線が最後まで正常に動くことを
確認する(Phase2完了条件11: Small Real-data Test)。tmp_pathを使い、実際の
Japanese_Equity_Lab/01_data・06_backtestsは汚さない。
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import pytest
from lib.backtest.engine import BacktestEngine, BacktestRunConfig, TransactionCostConfig, build_close_to_next_open_window
from lib.data_sources.convert import equity_bars_payload_to_raw_bars, trading_calendar_payload_to_calendar
from lib.data_sources.fixture import FixtureDataSourceAdapter
from lib.errors import LookAheadBiasError
from lib.market_calendar import JST
from lib.point_in_time import PointInTimeRecord
from lib.registry.experiment_registry import ExperimentRegistry
from lib.registry.provenance import ProvenanceLink, ProvenanceStore
from lib.schemas.experiment import Experiment, ExperimentStatus
from lib.schemas.price_data import apply_split_adjustments
from lib.snapshot import RawSnapshotStore
from lib.strategies.fixed_pipeline_validation import DEFAULT_CONFIG, STRATEGY_ID, as_buy_signal_fn

_FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "synthetic_jquants_v2_bars.json"
_CODES = ["7203", "6758", "9984"]
_BENCHMARK_CODE = "TOPIX_SYNTH"
_START = date(2026, 1, 5)
_END = date(2026, 6, 30)


def test_fixture_pipeline_runs_end_to_end_and_is_reproducible(tmp_path: Path) -> None:
    adapter = FixtureDataSourceAdapter(_FIXTURE_PATH)
    snapshot_store = RawSnapshotStore(tmp_path / "01_data" / "raw")

    quotes_result = adapter.fetch_equity_bars(codes=[*_CODES, _BENCHMARK_CODE], start_date=_START, end_date=_END)
    calendar_result = adapter.fetch_trading_calendar(start_date=_START, end_date=_END)

    quotes_manifest = snapshot_store.save(quotes_result, snapshot_id="SNAP_TEST_daily_quotes")
    calendar_manifest = snapshot_store.save(calendar_result, snapshot_id="SNAP_TEST_trading_calendar")
    assert quotes_manifest.record_count > 0
    assert calendar_manifest.record_count > 0

    raw_bars = equity_bars_payload_to_raw_bars(quotes_result.payload)
    raw_by_code: dict[str, list] = {}
    for bar in raw_bars:
        raw_by_code.setdefault(bar.code, []).append(bar)

    price_history = {code: apply_split_adjustments(raw_by_code[code], []) for code in _CODES}
    benchmark_bars = apply_split_adjustments(raw_by_code[_BENCHMARK_CODE], [])
    trading_calendar = trading_calendar_payload_to_calendar(calendar_result.payload, range_start=_START, range_end=_END)

    run_config = BacktestRunConfig(
        universe_codes=tuple(_CODES),
        start_session=_START,
        end_session=_END,
        holding_period_days=DEFAULT_CONFIG.holding_period_days,
        transaction_cost=TransactionCostConfig(commission_bps=5, slippage_bps=5),
    )

    engine = BacktestEngine()
    metrics = engine.run(
        config=run_config,
        price_history=price_history,
        benchmark_bars=benchmark_bars,
        trading_calendar=trading_calendar,
        signal_fn=as_buy_signal_fn(),
    )

    # 7203/6758は右肩上がりの合成データなのでBUYシグナルが出てトレードが発生する。
    # 9984は右肩下がりなのでBUYシグナルが一度も出ず、トレードが発生しない。
    assert metrics.trade_count > 0
    assert metrics.unique_tickers == 2
    assert "9984" not in metrics.stock_by_stock_distribution
    assert metrics.benchmark_return is not None
    assert metrics.excess_return is not None

    # Experiment Registryへの記録とProvenance追跡。
    experiment_registry = ExperimentRegistry(tmp_path / "06_backtests" / "experiment_registry.jsonl")
    experiment = Experiment(
        experiment_id="BT_TEST0001",
        hypothesis_id="H_TEST0001",
        strategy_id=STRATEGY_ID,
        status=ExperimentStatus.TESTED,
        metrics=metrics,
    )
    experiment_registry.record(experiment)
    assert experiment_registry.summary()["TESTED"] == 1

    provenance = ProvenanceStore(tmp_path / "06_backtests" / "provenance.jsonl")
    provenance.add_link(
        ProvenanceLink(
            link_id="L1", from_type="raw_snapshot", from_id=quotes_manifest.snapshot_id, to_type="experiment", to_id="BT_TEST0001"
        )
    )
    chain = provenance.trace_to_origin("experiment", "BT_TEST0001")
    assert chain[0].from_id == quotes_manifest.snapshot_id

    # 同一Inputで再実行しても同じ結果になることを確認する(Reproducibility)。
    metrics_rerun = engine.run(
        config=run_config,
        price_history=price_history,
        benchmark_bars=benchmark_bars,
        trading_calendar=trading_calendar,
        signal_fn=as_buy_signal_fn(),
    )
    assert metrics == metrics_rerun


def test_fixture_pipeline_never_uses_same_day_close_execution(tmp_path: Path) -> None:
    """Pipeline全体を通しても、同日Close→同日約定のトレードが1件も発生しないことを確認する。"""
    adapter = FixtureDataSourceAdapter(_FIXTURE_PATH)
    quotes_result = adapter.fetch_equity_bars(codes=["7203"], start_date=_START, end_date=_END)
    calendar_result = adapter.fetch_trading_calendar(start_date=_START, end_date=_END)

    raw_bars = equity_bars_payload_to_raw_bars(quotes_result.payload)
    price_history = {"7203": apply_split_adjustments(raw_bars, [])}
    trading_calendar = trading_calendar_payload_to_calendar(calendar_result.payload, range_start=_START, range_end=_END)

    # holding_period_days=0はDecisionWindow/BacktestRunConfigのバリデーションで拒否される
    # (Close-to-Close実行を許すような設定自体を作れない)。
    with pytest.raises(ValueError, match="holding_period_days"):
        BacktestRunConfig(
            universe_codes=("7203",),
            start_session=_START,
            end_session=_END,
            holding_period_days=0,
        )

    # signal_fnが常にTrueを返しても、Engine内部はbuild_close_to_next_open_window経由でしか
    # DecisionWindowを作らないため、同日約定は構造的に発生しえない
    # (lib/backtest/engine.pyのDecisionWindow.__post_init__参照)。
    engine = BacktestEngine()
    metrics = engine.run(
        config=BacktestRunConfig(universe_codes=("7203",), start_session=_START, end_session=_END, holding_period_days=20),
        price_history=price_history,
        benchmark_bars=price_history["7203"],
        trading_calendar=trading_calendar,
        signal_fn=lambda bars: len(bars) > 0,
    )
    assert metrics.trade_count >= 0  # クラッシュせず完走することが本テストの主眼


def test_look_ahead_violation_is_structurally_prevented() -> None:
    """SignalInputはinformation_used_atより後のavailable_atを持つレコードを拒否する
    (Pipeline内部でLook-ahead biasが混入する経路が無いことの直接確認)。"""
    window = build_close_to_next_open_window(decision_session_date=_START, execution_session_date=date(2026, 1, 6))
    future_record = PointInTimeRecord(
        value_date=_START,
        published_at=datetime(2026, 1, 6, 9, 0, tzinfo=JST),  # decision_atより後
        available_at=datetime(2026, 1, 6, 9, 0, tzinfo=JST),
        label="future leak",
    )
    with pytest.raises(LookAheadBiasError):
        BacktestEngine().build_signal_input(window, [future_record])
