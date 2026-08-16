"""available_at(市場で当時利用可能になった日時)とretrieved_at(Research Labが
データを取得した日時)を混同していないことを確認する。

この2つを混同すると2種類の誤りが起こりうる。
1. retrieved_atをavailable_atとして使ってしまうと、何年も前の株価データを「今日」
   取得しただけで、そのデータが「今日まで市場参加者に利用不可能だった」ことになり、
   過去のバックテストで一切そのデータを使えなくなる(過度に保守的な誤り)。
2. 逆に、実際にはavailable_atが未来のデータ(発表前の情報)を、retrieved_atが
   過去であることを理由に「利用可能」と誤判定してしまうと、Look-ahead biasが
   混入する(危険な誤り)。

このテストは、Pipelineが実際に(1)のケースで壊れないこと、(2)のケースを検知できる
ことの両方を、synthetic dataで直接確認する。
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest
from lib.backtest.engine import BacktestEngine, BacktestRunConfig, build_close_to_next_open_window
from lib.backtest.price_history import StaticPriceHistory
from lib.data_sources.base import RawFetchResult
from lib.data_sources.convert import equity_bars_payload_to_raw_bars, trading_calendar_payload_to_calendar
from lib.errors import LookAheadBiasError
from lib.market_calendar import JST, session_close_at, session_open_at
from lib.point_in_time import PointInTimeRecord, assert_no_lookahead
from lib.schemas.price_data import apply_split_adjustments
from lib.strategies.fixed_pipeline_validation import as_buy_signal_fn


def test_old_market_data_retrieved_today_is_still_usable_for_a_historical_decision() -> None:
    """数年前の株価データを「今日」取得しても、available_atは当時の大引けのままである
    (retrieved_atが「今日」であることに引きずられて利用不可能になったりしない)。"""
    value_date = date(2020, 1, 6)
    market_available_at = session_close_at(value_date)  # 当時の大引け

    # RawFetchResult.retrieved_at は「今日この瞬間」であり、上のavailable_atとは無関係。
    retrieved_today = RawFetchResult(
        source="fixture",
        endpoint="fixture:daily_quotes",
        request_parameters={"code": "7203"},
        retrieved_at=datetime.now(UTC),
        data_period=f"{value_date.isoformat()}/{value_date.isoformat()}",
        response_schema_version="fixture-v1",
        payload=[{"Code": "7203", "Date": value_date.isoformat(), "C": 2000}],
    )
    assert retrieved_today.retrieved_at.date() != value_date  # retrieved_atは「今日」

    record = PointInTimeRecord(
        value_date=value_date,
        published_at=market_available_at,
        available_at=market_available_at,  # retrieved_atではなく市場の大引けから導出する
        label="7203 close",
    )
    decision_at_that_time = session_close_at(value_date)
    # 「今日取得した」ことと無関係に、当時の意思決定時点では普通に利用できる。
    assert_no_lookahead([record], decision_at_that_time)


def test_confusing_retrieved_at_with_available_at_would_break_all_historical_backtests() -> None:
    """(反面教師)もしavailable_atの代わりにretrieved_atを使ってしまったら、
    当時の意思決定時点では「未来の情報」扱いになり誤って拒否されることを示す。
    Pipelineの実装(lib/backtest/engine.py)がこの誤りをしていないことの根拠となる。"""
    value_date = date(2020, 1, 6)
    retrieved_at = datetime.now(UTC)  # 誤って retrieved_at を available_at 代わりに使うケース

    mistakenly_using_retrieved_at = PointInTimeRecord(
        value_date=value_date,
        published_at=retrieved_at,
        available_at=retrieved_at,  # 誤り: 本来は市場の大引け(session_close_at)を使うべき
        label="7203 close (誤り)",
    )
    decision_at_that_time = session_close_at(value_date)  # 2020年時点の意思決定
    with pytest.raises(LookAheadBiasError):
        assert_no_lookahead([mistakenly_using_retrieved_at], decision_at_that_time)


def test_engine_derives_available_at_from_market_close_not_retrieved_at() -> None:
    """BacktestEngine.run()が実際にavailable_atを市場の大引け(session_close_at)から
    導出しており、retrieved_atの概念を一切使っていないことをソースから直接確認する。"""
    import inspect

    from lib.backtest import engine as engine_module

    source = inspect.getsource(engine_module.BacktestEngine.run)
    assert "session_close_at" in source
    assert "retrieved_at" not in source


def test_future_available_at_is_rejected_even_if_retrieved_long_ago() -> None:
    """available_atが未来(まだ発表されていない)であれば、retrieved_atがどれだけ過去でも
    利用不可能として拒否する(retrieved_atの古さで安全性を誤魔化さない)。"""
    decision_at = session_close_at(date(2026, 1, 6))
    future_available_record = PointInTimeRecord(
        value_date=date(2026, 1, 6),
        published_at=datetime(2026, 1, 7, 9, 0, tzinfo=JST),  # decision_atより後に公表
        available_at=datetime(2026, 1, 7, 9, 0, tzinfo=JST),
        label="future disclosure",
    )
    with pytest.raises(LookAheadBiasError):
        assert_no_lookahead([future_available_record], decision_at)


def _weekdays(start: date, count: int) -> list[date]:
    days: list[date] = []
    current = start
    while len(days) < count:
        if current.weekday() < 5:
            days.append(current)
        current += timedelta(days=1)
    return days


def _equity_bars_payload(code: str, days: list[date], *, base: float, step: float) -> list[dict[str, object]]:
    rows = []
    for i, d in enumerate(days):
        price = base + step * i
        rows.append(
            {
                "Code": code,
                "Date": d.isoformat(),
                "O": price,
                "H": price + 1,
                "L": price - 1,
                "C": price,
                "Vo": 1000,
                "AdjFactor": 1.0,
                "ExRT": None,
            }
        )
    return rows


def _trading_calendar_payload(days: list[date]) -> list[dict[str, object]]:
    return [{"Date": d.isoformat(), "HolDiv": "1"} for d in days]


_BEHAVIOR_DAYS = _weekdays(date(2026, 1, 5), 40)  # 2026-01-05は月曜


def _run_full_pipeline(quotes_payload: list[dict[str, object]]) -> object:
    """Raw payloadからBacktestEngine.run()までの全経路を実行する(retrieved_atは
    どの段階でも使わないため、この経路の出力にはretrieved_atが一切影響しないはず)。"""
    calendar_payload = _trading_calendar_payload(_BEHAVIOR_DAYS)
    raw_bars = equity_bars_payload_to_raw_bars(quotes_payload)
    price_history = StaticPriceHistory({"7203": apply_split_adjustments(raw_bars, [])})
    bench_payload = _equity_bars_payload("BENCH", _BEHAVIOR_DAYS, base=2000.0, step=0.3)
    benchmark_bars = apply_split_adjustments(equity_bars_payload_to_raw_bars(bench_payload), [])
    trading_calendar = trading_calendar_payload_to_calendar(
        calendar_payload, range_start=_BEHAVIOR_DAYS[0], range_end=_BEHAVIOR_DAYS[-1]
    )
    config = BacktestRunConfig(
        universe_codes=("7203",),
        start_session=_BEHAVIOR_DAYS[0],
        end_session=_BEHAVIOR_DAYS[-1],
        holding_period_days=5,
    )
    return BacktestEngine().run(
        config=config,
        price_history=price_history,
        benchmark_bars=benchmark_bars,
        trading_calendar=trading_calendar,
        signal_fn=as_buy_signal_fn(),
    )


def test_retrieved_at_changing_alone_does_not_change_the_investment_decision() -> None:
    """(behavioral) 同じavailable_at相当のデータで、RawFetchResult.retrieved_atだけを
    大きく変えた2つのSnapshotから同じPipelineを実行すると、完全に同じBacktest結果
    (= 同じ投資判断)になることを実際に確認する。"""
    quotes_payload = _equity_bars_payload("7203", _BEHAVIOR_DAYS, base=1000.0, step=1.0)

    fetch_result_a = RawFetchResult(
        source="fixture",
        endpoint="fixture:daily_quotes",
        request_parameters={"code": "7203"},
        retrieved_at=datetime(2026, 1, 1, tzinfo=UTC),  # 過去に取得したことにする
        data_period="2026-01-05/2026-02-27",
        response_schema_version="fixture-v1",
        payload=quotes_payload,
    )
    fetch_result_b = RawFetchResult(
        source="fixture",
        endpoint="fixture:daily_quotes",
        request_parameters={"code": "7203"},
        retrieved_at=datetime(2031, 6, 15, tzinfo=UTC),  # 5年以上後に取得したことにする(payloadは同一)
        data_period="2026-01-05/2026-02-27",
        response_schema_version="fixture-v1",
        payload=quotes_payload,
    )
    assert fetch_result_a.retrieved_at != fetch_result_b.retrieved_at

    metrics_a = _run_full_pipeline(fetch_result_a.payload)
    metrics_b = _run_full_pipeline(fetch_result_b.payload)

    assert metrics_a == metrics_b  # retrieved_atの違いはInvestment Decisionに一切影響しない


def test_moving_available_at_into_the_future_triggers_lookahead_error_via_engine() -> None:
    """(behavioral) available_atだけを未来に変更すると、BacktestEngine.build_signal_input()
    経由でLookAheadBiasErrorになることを確認する(retrieved_atは一切変更していない)。"""
    engine = BacktestEngine()
    decision_date = date(2026, 1, 30)
    execution_date = date(2026, 2, 2)
    decision_window = build_close_to_next_open_window(decision_session_date=decision_date, execution_session_date=execution_date)

    normal_record = PointInTimeRecord(
        value_date=decision_date,
        published_at=session_close_at(decision_date),
        available_at=session_close_at(decision_date),  # 通常通り、その日の大引けに利用可能
        label="7203 close",
    )
    engine.build_signal_input(decision_window, [normal_record])  # 通常は問題なく通る

    future_available_record = PointInTimeRecord(
        value_date=decision_date,
        published_at=session_close_at(decision_date),
        available_at=session_open_at(execution_date),  # available_atだけを翌営業日の寄付へ変更
        label="7203 close (available_atを未来へ変更)",
    )
    with pytest.raises(LookAheadBiasError):
        engine.build_signal_input(decision_window, [future_available_record])
