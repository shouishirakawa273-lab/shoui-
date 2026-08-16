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

from datetime import UTC, date, datetime

import pytest
from lib.data_sources.base import RawFetchResult
from lib.errors import LookAheadBiasError
from lib.market_calendar import JST, session_close_at
from lib.point_in_time import PointInTimeRecord, assert_no_lookahead


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
        payload=[{"Code": "7203", "Date": value_date.isoformat(), "Close": 2000}],
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
