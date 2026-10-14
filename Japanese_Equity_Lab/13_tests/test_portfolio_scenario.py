"""Portfolio Simulationの挙動確認専用テスト。

`13_tests/fixtures/portfolio_scenario_v2.json`(J-Quants API V2形状)は、Strategy
Performance評価には使わないSystem Behavior Test専用のsynthetic fixtureである。
以下を意図的に1本のシナリオへ詰め込んでいる。

- 異なる日付・異なる銘柄(PSIM_A / PSIM_B)へのSignal
- 保有中の再Signal(PositionPolicy.NO_REENTRY_WHILE_POSITION_OPENでSKIPされる)
- Open価格欠損によるExecution Failure(UNEXECUTABLE_NO_OPEN)
- 正常なExecutionとExit

Signalの発生日は、モメンタム計算等の間接的な条件ではなく、fixtureの`_scenario`に
記載された日付をそのまま使う専用のsignal_fnで直接指定する(このFixtureで
どの戦略が儲かるかを検証したいわけではないため)。
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import date
from pathlib import Path

from lib.backtest.engine import (
    BacktestEngine,
    BacktestRunConfig,
    ExecutionOutcome,
)
from lib.backtest.price_history import StaticPriceHistory
from lib.data_sources.convert import equity_bars_payload_to_raw_bars, trading_calendar_payload_to_calendar
from lib.schemas.price_data import AdjustedOHLCVBar, apply_split_adjustments

_FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "portfolio_scenario_v2.json"


def _load_fixture() -> dict[str, object]:
    return json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))


def _signal_dates_from_fixture(fixture: dict[str, object]) -> dict[str, set[date]]:
    scenario = fixture["_scenario"]  # type: ignore[index]
    raw = scenario["signal_dates"]  # type: ignore[index]
    return {code: {date.fromisoformat(d) for d in dates} for code, dates in raw.items()}  # type: ignore[union-attr]


def test_portfolio_scenario_fixture_is_marked_as_system_behavior_test_only() -> None:
    fixture = _load_fixture()
    assert "Strategy Performance評価には使用しないでください" in fixture["_disclaimer"]  # type: ignore[index]


def test_portfolio_scenario_exercises_policy_skip_execution_failure_and_normal_flow() -> None:
    fixture = _load_fixture()
    signal_dates = _signal_dates_from_fixture(fixture)

    def scenario_signal_fn(bars_up_to_decision: Sequence[AdjustedOHLCVBar]) -> bool:
        if not bars_up_to_decision:
            return False
        last = bars_up_to_decision[-1]
        return last.session_date in signal_dates.get(last.code, set())

    quotes = fixture["equity_bars"]  # type: ignore[assignment]
    codes = ["PSIM_A", "PSIM_B"]
    price_history_by_code = {}
    for code in codes:
        raw_bars = equity_bars_payload_to_raw_bars(quotes[code])  # type: ignore[index]
        price_history_by_code[code] = apply_split_adjustments(raw_bars, [])
    price_history = StaticPriceHistory(price_history_by_code)

    benchmark_raw = equity_bars_payload_to_raw_bars(quotes["PSIM_BENCH"])  # type: ignore[index]
    benchmark_bars = apply_split_adjustments(benchmark_raw, [])

    calendar_payload = fixture["trading_calendar"]  # type: ignore[assignment]
    all_dates = [date.fromisoformat(row["Date"]) for row in calendar_payload]  # type: ignore[index]
    trading_calendar = trading_calendar_payload_to_calendar(
        calendar_payload, range_start=min(all_dates), range_end=max(all_dates)
    )

    holding_period_days = fixture["_scenario"]["holding_period_days"]  # type: ignore[index]
    config = BacktestRunConfig(
        universe_codes=tuple(codes),
        start_session=min(all_dates),
        end_session=max(all_dates),
        holding_period_days=holding_period_days,  # type: ignore[arg-type]
    )

    metrics = BacktestEngine().run(
        config=config,
        price_history=price_history,
        benchmark_bars=benchmark_bars,
        trading_calendar=trading_calendar,
        signal_fn=scenario_signal_fn,
    )

    # シナリオ通りの内訳になっていることを直接確認する。
    # PSIM_A: idx5(EXECUTED) / idx8(SKIPPED_POSITION_OPEN) / idx12(UNEXECUTABLE_NO_OPEN) / idx15(EXECUTED)
    # PSIM_B: idx3(EXECUTED)
    assert metrics.signal_count == 5
    assert metrics.executed_count == 3  # PSIM_A x2 + PSIM_B x1
    assert metrics.policy_skipped_count == 1  # PSIM_Aの保有中再Signal
    assert metrics.execution_failed_count == 1  # PSIM_AのOpen欠損
    assert metrics.execution_outcomes == {
        ExecutionOutcome.EXECUTED.value: 3,
        ExecutionOutcome.SKIPPED_POSITION_OPEN.value: 1,
        ExecutionOutcome.UNEXECUTABLE_NO_OPEN.value: 1,
    }
    assert metrics.unique_tickers == 2  # PSIM_A, PSIM_B ともに少なくとも1件は成立
    # PSIM_Aの2回のEXECUTEDトレードは異なる日にentryしている(idx6とidx16)。
    assert metrics.unique_entry_dates == 3
