from __future__ import annotations

from datetime import date, datetime

import pytest
from lib.backtest.engine import (
    BacktestEngine,
    DataSplit,
    DecisionWindow,
    TradeResult,
    build_close_to_next_open_window,
    compute_metrics,
)
from lib.errors import LookAheadBiasError
from lib.market_calendar import JST, session_close_at, session_open_at
from lib.point_in_time import PointInTimeRecord


def _close_to_next_open_window(decision_date: date, execution_date: date) -> DecisionWindow:
    return build_close_to_next_open_window(decision_session_date=decision_date, execution_session_date=execution_date)


def test_build_signal_input_accepts_available_records() -> None:
    engine = BacktestEngine()
    record = PointInTimeRecord(
        value_date=date(2026, 8, 17),
        published_at=datetime(2026, 8, 17, 9, 0, tzinfo=JST),
        available_at=datetime(2026, 8, 17, 9, 0, tzinfo=JST),
        label="PER",
    )
    window = _close_to_next_open_window(date(2026, 8, 17), date(2026, 8, 18))
    signal_input = engine.build_signal_input(window, [record])
    assert signal_input.records == (record,)


def test_build_signal_input_rejects_after_hours_disclosure_on_same_day_close() -> None:
    """information_used_at(15:30) > 開示時刻(16:00) のデータはBacktestが拒否する。"""
    engine = BacktestEngine()
    late_earnings = PointInTimeRecord(
        value_date=date(2026, 8, 17),
        published_at=datetime(2026, 8, 17, 16, 0, tzinfo=JST),
        available_at=datetime(2026, 8, 17, 16, 0, tzinfo=JST),
        label="Q1決算(引け後開示)",
    )
    window = _close_to_next_open_window(date(2026, 8, 17), date(2026, 8, 18))
    with pytest.raises(LookAheadBiasError):
        engine.build_signal_input(window, [late_earnings])


def test_decision_window_rejects_execution_before_decision() -> None:
    with pytest.raises(ValueError, match="information_used_at"):
        DecisionWindow(
            information_used_at=datetime(2026, 8, 17, 9, 0, tzinfo=JST),
            decision_at=datetime(2026, 8, 17, 15, 30, tzinfo=JST),
            execution_at=datetime(2026, 8, 17, 9, 0, tzinfo=JST),
        )


def test_decision_window_rejects_information_used_after_decision() -> None:
    with pytest.raises(ValueError, match="information_used_at"):
        DecisionWindow(
            information_used_at=datetime(2026, 8, 17, 16, 0, tzinfo=JST),
            decision_at=datetime(2026, 8, 17, 15, 30, tzinfo=JST),
            execution_at=datetime(2026, 8, 18, 9, 0, tzinfo=JST),
        )


def test_close_to_close_execution_is_rejected() -> None:
    """当日Closeの情報で意思決定した場合、同日中の価格では約定できない。"""
    close_at = session_close_at(date(2026, 8, 17))
    with pytest.raises(LookAheadBiasError, match="Close-to-Close"):
        DecisionWindow(
            information_used_at=close_at,
            decision_at=close_at,
            # 同日の(架空の)遅い時刻を約定時刻にしても許されない。
            execution_at=datetime(2026, 8, 17, 23, 0, tzinfo=JST),
        )


def test_default_execution_model_is_next_session_open() -> None:
    window = build_close_to_next_open_window(decision_session_date=date(2026, 8, 17), execution_session_date=date(2026, 8, 18))
    assert window.decision_at == session_close_at(date(2026, 8, 17))
    assert window.execution_at == session_open_at(date(2026, 8, 18))


def test_build_close_to_next_open_window_rejects_non_later_session() -> None:
    with pytest.raises(LookAheadBiasError):
        build_close_to_next_open_window(decision_session_date=date(2026, 8, 17), execution_session_date=date(2026, 8, 17))


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
