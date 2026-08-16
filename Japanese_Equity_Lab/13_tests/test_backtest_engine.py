from __future__ import annotations

from datetime import date, datetime

import pytest
from lib.backtest.engine import (
    BacktestEngine,
    DataSplit,
    DecisionWindow,
    TradeResult,
    compute_metrics,
)
from lib.errors import LookAheadBiasError
from lib.point_in_time import JST, PointInTimeRecord, session_close_at


def _window(session_date: date) -> DecisionWindow:
    return DecisionWindow(
        decision_at=session_close_at(session_date),
        execution_at=datetime.combine(date(2026, 8, 18), datetime.min.time(), tzinfo=JST),
    )


def test_build_signal_input_accepts_available_records() -> None:
    engine = BacktestEngine()
    record = PointInTimeRecord(
        value_date=date(2026, 8, 17),
        published_at=datetime(2026, 8, 17, 9, 0, tzinfo=JST),
        available_at=datetime(2026, 8, 17, 9, 0, tzinfo=JST),
        label="PER",
    )
    signal_input = engine.build_signal_input(_window(date(2026, 8, 17)), [record])
    assert signal_input.records == (record,)


def test_build_signal_input_rejects_after_hours_disclosure_on_same_day_close() -> None:
    """available_at(15:30) > decision_at(同日15:00大引け) のデータはBacktestが拒否する。"""
    engine = BacktestEngine()
    late_earnings = PointInTimeRecord(
        value_date=date(2026, 8, 17),
        published_at=datetime(2026, 8, 17, 15, 30, tzinfo=JST),
        available_at=datetime(2026, 8, 17, 15, 30, tzinfo=JST),
        label="Q1決算(引け後開示)",
    )
    with pytest.raises(LookAheadBiasError):
        engine.build_signal_input(_window(date(2026, 8, 17)), [late_earnings])


def test_decision_window_rejects_execution_before_decision() -> None:
    with pytest.raises(ValueError, match="execution_at"):
        DecisionWindow(
            decision_at=datetime(2026, 8, 17, 15, 0, tzinfo=JST),
            execution_at=datetime(2026, 8, 17, 9, 0, tzinfo=JST),
        )


def test_compute_metrics_basic_distribution() -> None:
    trades = [
        TradeResult(code="7203", sector="Auto", year=2025, net_pretax_return=0.05),
        TradeResult(code="7203", sector="Auto", year=2026, net_pretax_return=-0.02),
        TradeResult(code="9984", sector="Tech", year=2026, net_pretax_return=0.10),
    ]
    metrics = compute_metrics(
        trades,
        data_split=DataSplit.TEST,
        benchmark_return=0.03,
        sector_benchmark_return=0.04,
        transaction_cost_bps=10,
    )
    assert metrics.sample_size == 2
    assert metrics.trade_count == 3
    assert metrics.win_rate == pytest.approx(2 / 3)
    assert metrics.excess_return is not None
    assert metrics.year_by_year_performance[2026] == pytest.approx((-0.02 + 0.10) / 2)
    assert metrics.sector_by_sector_performance["Auto"] == pytest.approx((0.05 - 0.02) / 2)
    assert metrics.stock_by_stock_distribution["9984"] == pytest.approx(0.10)


def test_compute_metrics_empty_trades_returns_none_stats() -> None:
    metrics = compute_metrics([], data_split=DataSplit.TRAIN)
    assert metrics.sample_size == 0
    assert metrics.trade_count == 0
    assert metrics.average_return is None
    assert metrics.win_rate is None


def test_run_is_not_implemented_in_phase1() -> None:
    with pytest.raises(NotImplementedError):
        BacktestEngine().run()
