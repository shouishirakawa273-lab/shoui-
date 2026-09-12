from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest
from lib.backtest.engine import (
    BacktestEngine,
    BacktestRunConfig,
    BenchmarkDataInsufficientError,
    DataSplit,
    DecisionWindow,
    ExecutionOutcome,
    PositionPolicy,
    TradeResult,
    TransactionCostConfig,
    build_close_to_next_open_window,
    compute_metrics,
)
from lib.backtest.price_history import StaticPriceHistory
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
        TradeResult(code="7203", sector="Auto", year=2025, entry_date=date(2025, 6, 2), net_pretax_return=0.05),
        TradeResult(code="7203", sector="Auto", year=2026, entry_date=date(2026, 1, 6), net_pretax_return=-0.02),
        TradeResult(code="9984", sector="Tech", year=2026, entry_date=date(2026, 1, 6), net_pretax_return=0.10),
    ]
    metrics = compute_metrics(
        trades,
        data_split=DataSplit.TEST,
        benchmark_return=0.03,
        sector_benchmark_return=0.04,
        transaction_cost_bps=10,
        signal_count=5,
        execution_outcomes={"EXECUTED": 3, "SKIPPED_POSITION_OPEN": 2},
    )
    assert metrics.unique_tickers == 2
    assert metrics.trade_count == 3
    assert metrics.unique_entry_dates == 2  # 2025-06-02 と 2026-01-06(2件重複)
    assert metrics.signal_count == 5
    # SKIPPED_POSITION_OPENはPolicy Skipであり、Execution Failureとは別集計される。
    assert metrics.policy_skipped_count == 2
    assert metrics.order_attempt_count == 3  # signal_count(5) - policy_skipped_count(2)
    assert metrics.executed_count == 3
    assert metrics.execution_failed_count == 0  # order_attempt_count(3) - executed_count(3)
    assert metrics.signal_to_trade_rate == pytest.approx(3 / 5)
    assert metrics.order_execution_rate == pytest.approx(3 / 3)
    assert metrics.execution_outcomes == {"EXECUTED": 3, "SKIPPED_POSITION_OPEN": 2}
    assert metrics.win_rate == pytest.approx(2 / 3)
    assert metrics.excess_return is not None
    assert metrics.year_by_year_performance[2026] == pytest.approx((-0.02 + 0.10) / 2)
    assert metrics.sector_by_sector_performance["Auto"] == pytest.approx((0.05 - 0.02) / 2)
    assert metrics.stock_by_stock_distribution["9984"] == pytest.approx(0.10)
    # Post-Phase5 Hardening A(D0069): 銘柄別trade数・trade数シェア。
    assert metrics.stock_by_stock_trade_count == {"7203": 2, "9984": 1}
    assert metrics.stock_by_stock_trade_share["7203"] == pytest.approx(2 / 3)
    assert metrics.stock_by_stock_trade_share["9984"] == pytest.approx(1 / 3)


def test_compute_metrics_stock_by_stock_trade_share_empty_when_no_trades() -> None:
    """trade件数0の場合、stock_by_stock_trade_shareはZeroDivisionを起こさず空dictになる。"""
    metrics = compute_metrics([], data_split=DataSplit.TEST, signal_count=0)
    assert metrics.stock_by_stock_trade_count == {}
    assert metrics.stock_by_stock_trade_share == {}
    assert metrics.stock_by_stock_distribution == {}


def test_compute_metrics_trade_concentration_visible_for_single_ticker_dominance() -> None:
    """少数銘柄への集中(旧BacktestMetricsでは事後検証できなかったGap、D0067/skeptic-reviewer指摘)を
    trade_countだけでなくtrade数・shareとして直接確認できる。"""
    trades = [
        TradeResult(code="7203", sector="Auto", year=2026, entry_date=date(2026, 1, 6), net_pretax_return=0.01),
        TradeResult(code="7203", sector="Auto", year=2026, entry_date=date(2026, 2, 3), net_pretax_return=0.02),
        TradeResult(code="7203", sector="Auto", year=2026, entry_date=date(2026, 3, 3), net_pretax_return=-0.01),
        TradeResult(code="6758", sector="Tech", year=2026, entry_date=date(2026, 4, 1), net_pretax_return=0.03),
    ]
    metrics = compute_metrics(trades, data_split=DataSplit.TEST, signal_count=4)
    assert metrics.stock_by_stock_trade_count == {"7203": 3, "6758": 1}
    assert metrics.stock_by_stock_trade_share["7203"] == pytest.approx(0.75)
    assert metrics.stock_by_stock_trade_share["6758"] == pytest.approx(0.25)


# --- Post-Phase5 Hardening B(Codex Transaction Cost Audit、D0070) -----------------------
# Finding1: Gross/Net Semantic Clarity


def test_trade_result_gross_pretax_return_alias_matches_net_pretax_return() -> None:
    """`net_pretax_return`という Field名は歴史的経緯によるもので、実際の格納値は
    取引コスト控除前のGross Returnである(D0070 Finding1)。新しいAliasが同じ値を
    返すことを確認する(Field名自体はBackward Compatibilityのため変更しない)。"""
    trade = TradeResult(code="7203", sector="Auto", year=2026, entry_date=date(2026, 1, 6), net_pretax_return=0.0321)
    assert trade.gross_pretax_return == trade.net_pretax_return == pytest.approx(0.0321)


def test_compute_metrics_gross_equals_net_at_zero_cost() -> None:
    trades = [TradeResult(code="7203", sector=None, year=2026, entry_date=date(2026, 1, 6), net_pretax_return=0.05)]
    metrics = compute_metrics(trades, data_split=DataSplit.TEST, transaction_cost_bps=0.0)
    assert metrics.average_return == pytest.approx(metrics.transaction_cost_adjusted_return)


def test_compute_metrics_net_below_gross_for_positive_finite_cost() -> None:
    trades = [TradeResult(code="7203", sector=None, year=2026, entry_date=date(2026, 1, 6), net_pretax_return=0.05)]
    metrics = compute_metrics(trades, data_split=DataSplit.TEST, transaction_cost_bps=10.0)
    assert metrics.transaction_cost_adjusted_return < metrics.average_return


# Finding2: excess_return Population Mismatch


def test_compute_metrics_excess_return_uses_pairwise_population_when_benchmark_missing_for_some_trades() -> None:
    """Trade1はBenchmarkが観測でき、Trade2は観測できない(D0070 Finding2の再現Case)。
    旧実装は`average_return`(全trade平均、Trade1+Trade2)と`benchmark_return`
    (観測できたTrade1のみの平均)という異なる母集団同士を引き算していた。
    修正後は`gross_excess_return`/`net_excess_return`/`excess_return`いずれも
    Trade1のみ(両方観測できたtrade)の母集団で計算されることを確認する。"""
    trades = [
        TradeResult(code="7203", sector=None, year=2026, entry_date=date(2026, 1, 6), net_pretax_return=0.10),
        TradeResult(code="6758", sector=None, year=2026, entry_date=date(2026, 2, 3), net_pretax_return=0.20),
    ]
    # Trade1(7203)はBenchmark観測できた(0.03)、Trade2(6758)は観測できない(None)。
    benchmark_returns_by_trade = [0.03, None]
    metrics = compute_metrics(
        trades,
        data_split=DataSplit.TEST,
        benchmark_return=0.03,  # 観測できたTrade1のみの平均(BacktestEngine.run()と同じ定義)
        transaction_cost_bps=10.0,
        benchmark_returns_by_trade=benchmark_returns_by_trade,
    )
    # Pairwise population(Trade1のみ)での差分。全trade平均(0.15)との差分ではない。
    assert metrics.gross_excess_return == pytest.approx(0.10 - 0.03)
    assert metrics.excess_return == pytest.approx(metrics.gross_excess_return)
    cost = 10.0 / 10_000
    assert metrics.net_excess_return == pytest.approx((0.10 - cost) - 0.03)
    # 旧実装(異なる母集団同士の差分)には一致しないことも明示的に確認する。
    mismatched_population_excess_return = metrics.average_return - 0.03  # 旧式: 全trade平均 - benchmark
    assert metrics.excess_return != pytest.approx(mismatched_population_excess_return)


def test_compute_metrics_excess_return_is_none_when_no_trade_has_matched_benchmark() -> None:
    """対応が取れるtradeが1件も無い場合、異なる母集団のまま残さずNoneにする(D0070 Finding2)。"""
    trades = [TradeResult(code="7203", sector=None, year=2026, entry_date=date(2026, 1, 6), net_pretax_return=0.10)]
    metrics = compute_metrics(trades, data_split=DataSplit.TEST, benchmark_return=None, benchmark_returns_by_trade=[None])
    assert metrics.gross_excess_return is None
    assert metrics.net_excess_return is None
    assert metrics.excess_return is None


def test_compute_metrics_excess_return_falls_back_to_legacy_formula_without_per_trade_benchmark() -> None:
    """`benchmark_returns_by_trade`を渡さない直接呼び出し(Event Study等)は、trade単位の
    対応情報が無いため従来通りscalar同士の単純差分にfallbackする(既存呼び出し元の後方互換)。"""
    trades = [
        TradeResult(code="7203", sector=None, year=2026, entry_date=date(2026, 1, 6), net_pretax_return=0.10),
        TradeResult(code="6758", sector=None, year=2026, entry_date=date(2026, 2, 3), net_pretax_return=0.20),
    ]
    metrics = compute_metrics(trades, data_split=DataSplit.TEST, benchmark_return=0.03)
    assert metrics.excess_return == pytest.approx(metrics.average_return - 0.03)
    assert metrics.gross_excess_return == pytest.approx(metrics.excess_return)


def test_compute_metrics_rejects_benchmark_returns_by_trade_with_mismatched_length() -> None:
    trades = [TradeResult(code="7203", sector=None, year=2026, entry_date=date(2026, 1, 6), net_pretax_return=0.10)]
    with pytest.raises(ValueError, match="benchmark_returns_by_trade"):
        compute_metrics(trades, data_split=DataSplit.TEST, benchmark_returns_by_trade=[0.03, 0.04])


# Finding4: Non-finite Cost


def test_transaction_cost_config_rejects_nan_commission() -> None:
    with pytest.raises(ValueError, match="有限"):
        TransactionCostConfig(commission_bps=float("nan"))


def test_transaction_cost_config_rejects_positive_infinity_slippage() -> None:
    with pytest.raises(ValueError, match="有限"):
        TransactionCostConfig(slippage_bps=float("inf"))


def test_transaction_cost_config_rejects_negative_infinity_commission() -> None:
    with pytest.raises(ValueError, match="有限"):
        TransactionCostConfig(commission_bps=float("-inf"))


def test_transaction_cost_config_still_rejects_negative_finite_values() -> None:
    with pytest.raises(ValueError, match="0以上"):
        TransactionCostConfig(commission_bps=-1.0)


def test_compute_metrics_distinguishes_policy_skip_from_execution_failure() -> None:
    """SKIPPED_POSITION_OPEN(Policy Skip)とUNEXECUTABLE_NO_OPEN(Execution Failure)を
    同じ「unexecuted」として合算しないことを直接確認する。"""
    trades = [TradeResult(code="7203", sector=None, year=2026, entry_date=date(2026, 1, 6), net_pretax_return=0.01)]
    metrics = compute_metrics(
        trades,
        data_split=DataSplit.TEST,
        signal_count=10,
        execution_outcomes={"EXECUTED": 1, "SKIPPED_POSITION_OPEN": 6, "UNEXECUTABLE_NO_OPEN": 3},
    )
    assert metrics.policy_skipped_count == 6  # Policy Skipのみ
    assert metrics.order_attempt_count == 4  # signal_count(10) - policy_skipped_count(6)
    assert metrics.execution_failed_count == 3  # order_attempt_count(4) - executed_count(1)
    assert metrics.executed_count == 1
    assert metrics.signal_to_trade_rate == pytest.approx(1 / 10)
    assert metrics.order_execution_rate == pytest.approx(1 / 4)


def test_compute_metrics_empty_trades_returns_none_stats() -> None:
    metrics = compute_metrics([], data_split=DataSplit.TRAIN)
    assert metrics.unique_tickers == 0
    assert metrics.trade_count == 0
    assert metrics.unique_entry_dates == 0
    assert metrics.signal_count == 0
    assert metrics.signal_to_trade_rate is None  # signal_countを渡さない場合はNone
    assert metrics.order_execution_rate is None
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
# 計82本以上あれば1トレードが完成する。NO_REENTRY_WHILE_POSITION_OPENの下で複数の
# (重ならない)トレードが完成するには、82本区切りが複数回入るだけの本数が必要。
_DAYS = _weekdays(date(2026, 1, 5), 220)  # 2026-01-05は月曜


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
    price_history = StaticPriceHistory({"7203": _uptrend_bars("7203", _DAYS, base=1000.0, step=1.0)})
    benchmark_bars = _uptrend_bars("TOPIX", _DAYS, base=2000.0, step=0.5)

    metrics = engine.run(
        config=_run_config(),
        price_history=price_history,
        benchmark_bars=benchmark_bars,
        trading_calendar=calendar,
        signal_fn=as_buy_signal_fn(),
    )

    assert metrics.trade_count > 0
    assert metrics.unique_tickers == 1
    assert metrics.average_return is not None and metrics.average_return > 0  # 右肩上がりの合成データなので正のリターン
    assert metrics.benchmark_return is not None
    assert metrics.excess_return is not None
    assert metrics.signal_count >= metrics.trade_count
    assert metrics.signal_to_trade_rate == pytest.approx(metrics.trade_count / metrics.signal_count)


def test_run_raises_when_benchmark_data_insufficient() -> None:
    """要求期間をBenchmarkデータが全区間カバーしない場合、都合よく切り詰めず失敗する。"""
    engine = BacktestEngine()
    calendar = TradingCalendar(trading_dates=frozenset(_DAYS), range_start=_DAYS[0], range_end=_DAYS[-1])
    price_history = StaticPriceHistory({"7203": _uptrend_bars("7203", _DAYS, base=1000.0, step=1.0)})
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
    price_history = StaticPriceHistory({"7203": bars})
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
        price_history=StaticPriceHistory({"7203": _uptrend_bars("7203", _DAYS, base=1000.0, step=1.0)}),
        benchmark_bars=benchmark_bars,
        trading_calendar=calendar,
        signal_fn=as_buy_signal_fn(),
    )
    # 欠損があった試行はUNEXECUTABLE_NO_OPENとして記録される(架空の価格で埋めない)。
    # NO_REENTRY_WHILE_POSITION_OPENの下では翌営業日に再試行が成功しうるため、
    # 最終的なtrade_countは変わらない場合があるが、失敗した試行自体は必ず記録される。
    assert metrics_with_gap.execution_outcomes.get(ExecutionOutcome.UNEXECUTABLE_NO_OPEN.value, 0) >= 1
    assert metrics_without_gap.execution_outcomes.get(ExecutionOutcome.UNEXECUTABLE_NO_OPEN.value, 0) == 0
    assert metrics_with_gap.execution_failed_count >= metrics_without_gap.execution_failed_count


def test_run_is_deterministic_given_identical_inputs() -> None:
    """同じRaw相当データ・同じStrategy・同じConfigなら同じBacktest結果になる(再現性)。"""
    engine = BacktestEngine()
    calendar = TradingCalendar(trading_dates=frozenset(_DAYS), range_start=_DAYS[0], range_end=_DAYS[-1])
    benchmark_bars = _uptrend_bars("TOPIX", _DAYS, base=2000.0, step=0.5)

    def _run() -> object:
        return engine.run(
            config=_run_config(transaction_cost=TransactionCostConfig(commission_bps=5, slippage_bps=3)),
            price_history=StaticPriceHistory({"7203": _uptrend_bars("7203", _DAYS, base=1000.0, step=1.0)}),
            benchmark_bars=benchmark_bars,
            trading_calendar=calendar,
            signal_fn=as_buy_signal_fn(),
        )

    first = _run()
    second = _run()
    assert first == second


def test_no_reentry_while_position_open_skips_overlapping_signals() -> None:
    """同一銘柄で既にポジションを保有している間の追加シグナルはSKIPPED_POSITION_OPENになり、
    holding期間が重なるトレードとして二重に計上されない(デフォルトのPositionPolicy)。"""
    engine = BacktestEngine()
    calendar = TradingCalendar(trading_dates=frozenset(_DAYS), range_start=_DAYS[0], range_end=_DAYS[-1])
    price_history = StaticPriceHistory({"7203": _uptrend_bars("7203", _DAYS, base=1000.0, step=1.0)})
    benchmark_bars = _uptrend_bars("TOPIX", _DAYS, base=2000.0, step=0.5)

    metrics = engine.run(
        config=_run_config(),
        price_history=price_history,
        benchmark_bars=benchmark_bars,
        trading_calendar=calendar,
        signal_fn=as_buy_signal_fn(),
    )

    # 右肩上がりの合成データなのでlookback以降ほぼ毎営業日シグナルが出るが、
    # NO_REENTRY_WHILE_POSITION_OPENにより実際のトレードはholding期間分空けてしか成立しない。
    assert metrics.signal_count > metrics.trade_count
    # Policy Skip(保有中の追加シグナル)・Censoring(期末近くでholding期間を観測できない)・
    # Execution Failureを同じ「unexecuted」として合算せず、別々に集計する(D0037)。
    assert metrics.policy_skipped_count == metrics.execution_outcomes.get(ExecutionOutcome.SKIPPED_POSITION_OPEN.value, 0)
    assert metrics.policy_skipped_count > 0
    assert metrics.censored_count == metrics.execution_outcomes.get(ExecutionOutcome.CENSORED_END_OF_SAMPLE.value, 0)
    assert metrics.execution_failed_count == metrics.execution_outcomes.get(ExecutionOutcome.OUTSIDE_DATA_RANGE.value, 0)
    assert (
        metrics.policy_skipped_count + metrics.censored_count + metrics.execution_failed_count
        == metrics.signal_count - metrics.trade_count
    )
    assert metrics.execution_outcomes.get(ExecutionOutcome.EXECUTED.value, 0) == metrics.trade_count
    assert metrics.signal_to_trade_rate == pytest.approx(metrics.trade_count / metrics.signal_count)
    assert metrics.order_execution_rate == pytest.approx(metrics.executed_count / metrics.eligible_order_attempt_count)
    # holding期間(60営業日)が重ならないよう空くため、複数トレードが成立していれば
    # entry日同士も60営業日以上離れているはず(=独立サンプルに近づく)。
    assert metrics.unique_entry_dates == metrics.trade_count


def test_signal_accounting_identity_across_policy_skip_censoring_and_execution_failure() -> None:
    """D0037: signal_count / policy_skipped_count / censored_count /
    eligible_order_attempt_count / executed_count / execution_failed_count の関係を
    1本のシナリオ(4分類すべてが同時に発生するデータ)で明確にする。

    signal_count == policy_skipped_count + censored_count + execution_failed_count + executed_count
    という会計恒等式が常に成り立つことを確認する(Right CensoringをExecution Failureに
    誤って合算しないという設計の直接確認)。
    """
    engine = BacktestEngine()
    calendar = TradingCalendar(trading_dates=frozenset(_DAYS), range_start=_DAYS[0], range_end=_DAYS[-1])
    bars = _uptrend_bars("7203", _DAYS, base=1000.0, step=1.0)
    # 21本目(最初のBUYシグナルの執行日)のOpenを欠損させ、期間の早い段階で
    # 真のExecution Failure(MISSING_PRICEではなくUNEXECUTABLE_NO_OPEN)を発生させる
    # (期末のCensoringとは別の、評価可能期間内の真の失敗であることを保証するため)。
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
    price_history = StaticPriceHistory({"7203": bars})
    benchmark_bars = _uptrend_bars("TOPIX", _DAYS, base=2000.0, step=0.5)

    metrics = engine.run(
        config=_run_config(),
        price_history=price_history,
        benchmark_bars=benchmark_bars,
        trading_calendar=calendar,
        signal_fn=as_buy_signal_fn(),
    )

    # 220営業日・holding=60・lookback=21という設定上、右肩上がりデータなら
    # 4分類すべてが実際に発生する(どれか1つでも0だとこのテストの意味が薄れるため確認する)。
    assert metrics.policy_skipped_count > 0
    assert metrics.censored_count > 0
    assert metrics.execution_failed_count > 0
    assert metrics.executed_count > 0

    # 会計恒等式そのもの。
    assert metrics.signal_count == (
        metrics.policy_skipped_count + metrics.censored_count + metrics.execution_failed_count + metrics.executed_count
    )
    # 中間集計(order_attempt_count / eligible_order_attempt_count)も整合していること。
    assert metrics.order_attempt_count == metrics.signal_count - metrics.policy_skipped_count
    assert metrics.eligible_order_attempt_count == metrics.order_attempt_count - metrics.censored_count
    assert metrics.execution_failed_count == metrics.eligible_order_attempt_count - metrics.executed_count
    # order_execution_rateはCensoringを除いた「評価可能な注文」だけを分母にする。
    assert metrics.order_execution_rate == pytest.approx(metrics.executed_count / metrics.eligible_order_attempt_count)


def test_default_position_policy_is_no_reentry_while_position_open() -> None:
    assert (
        BacktestRunConfig(
            universe_codes=("7203",), start_session=_DAYS[0], end_session=_DAYS[-1], holding_period_days=20
        ).position_policy
        == PositionPolicy.NO_REENTRY_WHILE_POSITION_OPEN
    )
