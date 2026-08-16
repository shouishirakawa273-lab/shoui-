from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest
from lib.backtest.engine import (
    BacktestEngine,
    BacktestRunConfig,
    BenchmarkDataInsufficientError,
    DataSplit,
    DecisionWindow,
    TradeResult,
    TransactionCostConfig,
    build_close_to_next_open_window,
    compute_metrics,
)
from lib.errors import LookAheadBiasError
from lib.market_calendar import JST, TradingCalendar, session_close_at, session_open_at
from lib.point_in_time import PointInTimeRecord
from lib.schemas.price_data import AdjustedOHLCVBar
from lib.strategies.fixed_pipeline_validation import DEFAULT_CONFIG, as_buy_signal_fn


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


def _weekdays(start: date, count: int) -> list[date]:
    days: list[date] = []
    current = start
    while len(days) < count:
        if current.weekday() < 5:
            days.append(current)
        current += timedelta(days=1)
    return days


def _uptrend_bars(code: str, days: list[date], *, base: float, step: float) -> list[AdjustedOHLCVBar]:
    bars = []
    for i, d in enumerate(days):
        price = base + step * i
        bars.append(
            AdjustedOHLCVBar(
                code=code,
                session_date=d,
                open=price,
                high=price + 1,
                low=price - 1,
                close=price,
                volume=1000.0,
                split_adjustment_factor=1.0,
                source="synthetic",
            )
        )
    return bars


# lookback(20)の起算に21本、entry用に1本、holding(60、DEFAULT_CONFIG準拠)分で
# 計82本以上あれば複数トレードが完成する。
_DAYS = _weekdays(date(2026, 1, 5), 100)  # 2026-01-05は月曜


def _run_config(**overrides: object) -> BacktestRunConfig:
    defaults: dict[str, object] = dict(
        universe_codes=("7203",),
        start_session=_DAYS[0],
        end_session=_DAYS[-1],
        holding_period_days=DEFAULT_CONFIG.holding_period_days,
    )
    defaults.update(overrides)
    return BacktestRunConfig(**defaults)  # type: ignore[arg-type]


def test_run_produces_trades_with_matched_benchmark_comparison() -> None:
    """Data -> Feature -> Signal -> Decision -> Execution -> Return -> Benchmark比較が一本通る。"""
    engine = BacktestEngine()
    calendar = TradingCalendar(trading_dates=frozenset(_DAYS), range_start=_DAYS[0], range_end=_DAYS[-1])
    price_history = {"7203": _uptrend_bars("7203", _DAYS, base=1000.0, step=1.0)}
    benchmark_bars = _uptrend_bars("TOPIX", _DAYS, base=2000.0, step=0.5)

    metrics = engine.run(
        config=_run_config(),
        price_history=price_history,
        benchmark_bars=benchmark_bars,
        trading_calendar=calendar,
        signal_fn=as_buy_signal_fn(),
    )

    assert metrics.trade_count > 0
    assert metrics.sample_size == 1
    assert metrics.average_return is not None and metrics.average_return > 0  # 右肩上がりの合成データなので正のリターン
    assert metrics.benchmark_return is not None
    assert metrics.excess_return is not None


def test_run_raises_when_benchmark_data_insufficient() -> None:
    """要求期間をBenchmarkデータが全区間カバーしない場合、都合よく切り詰めず失敗する。"""
    engine = BacktestEngine()
    calendar = TradingCalendar(trading_dates=frozenset(_DAYS), range_start=_DAYS[0], range_end=_DAYS[-1])
    price_history = {"7203": _uptrend_bars("7203", _DAYS, base=1000.0, step=1.0)}
    short_benchmark_bars = _uptrend_bars("TOPIX", _DAYS[:10], base=2000.0, step=0.5)  # 期間の一部しかない

    with pytest.raises(BenchmarkDataInsufficientError):
        engine.run(
            config=_run_config(),
            price_history=price_history,
            benchmark_bars=short_benchmark_bars,
            trading_calendar=calendar,
            signal_fn=as_buy_signal_fn(),
        )


def test_run_skips_trades_with_missing_execution_price_instead_of_fallback() -> None:
    """執行日の価格が欠損している場合、代替の価格へfallbackせずそのトレードをスキップする。"""
    engine = BacktestEngine()
    calendar = TradingCalendar(trading_dates=frozenset(_DAYS), range_start=_DAYS[0], range_end=_DAYS[-1])
    bars = _uptrend_bars("7203", _DAYS, base=1000.0, step=1.0)
    # 21本目(最初にBUYシグナルが出た次の営業日=執行日)のOpenを欠損させる。
    bars[21] = AdjustedOHLCVBar(
        code="7203",
        session_date=bars[21].session_date,
        open=None,
        high=None,
        low=None,
        close=bars[21].close,
        volume=1000.0,
        split_adjustment_factor=1.0,
        source="synthetic",
    )
    price_history = {"7203": bars}
    benchmark_bars = _uptrend_bars("TOPIX", _DAYS, base=2000.0, step=0.5)

    metrics_with_gap = engine.run(
        config=_run_config(),
        price_history=price_history,
        benchmark_bars=benchmark_bars,
        trading_calendar=calendar,
        signal_fn=as_buy_signal_fn(),
    )
    metrics_without_gap = engine.run(
        config=_run_config(),
        price_history={"7203": _uptrend_bars("7203", _DAYS, base=1000.0, step=1.0)},
        benchmark_bars=benchmark_bars,
        trading_calendar=calendar,
        signal_fn=as_buy_signal_fn(),
    )
    # 欠損があった分だけトレード数が減る(架空の価格で埋めて水増ししない)。
    assert metrics_with_gap.trade_count < metrics_without_gap.trade_count


def test_run_is_deterministic_given_identical_inputs() -> None:
    """同じRaw相当データ・同じStrategy・同じConfigなら同じBacktest結果になる(再現性)。"""
    engine = BacktestEngine()
    calendar = TradingCalendar(trading_dates=frozenset(_DAYS), range_start=_DAYS[0], range_end=_DAYS[-1])
    benchmark_bars = _uptrend_bars("TOPIX", _DAYS, base=2000.0, step=0.5)

    def _run() -> object:
        return engine.run(
            config=_run_config(transaction_cost=TransactionCostConfig(commission_bps=5, slippage_bps=3)),
            price_history={"7203": _uptrend_bars("7203", _DAYS, base=1000.0, step=1.0)},
            benchmark_bars=benchmark_bars,
            trading_calendar=calendar,
            signal_fn=as_buy_signal_fn(),
        )

    first = _run()
    second = _run()
    assert first == second
