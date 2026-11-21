"""Step 1 PIT窓の合成データテスト。PIT監査(2026-11-21)の指摘に対する回帰。

実APIには一切接続しない。
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest
from lib.backtest.price_history import StaticPriceHistory
from lib.market_calendar import JST, session_close_at
from lib.pretrade_risk.window import available_bars, require_aware
from lib.schemas.price_data import AdjustedOHLCVBar

SESSION = date(2026, 11, 20)


def _bar(session_date: date, *, code: str = "1234", close: float = 1000.0) -> AdjustedOHLCVBar:
    return AdjustedOHLCVBar(
        code=code,
        session_date=session_date,
        open=close,
        high=close,
        low=close,
        close=close,
        volume=10_000.0,
        split_adjustment_factor=1.0,
    )


def _source(bars: list[AdjustedOHLCVBar]) -> StaticPriceHistory:
    return StaticPriceHistory({"1234": bars})


def test_session_before_its_close_is_excluded() -> None:
    """[HIGH] 寄り前のas_ofに当日の未完セッションが混入しない。

    `bars_up_to` は `session_date <= as_of.date()` という日付粒度でしか
    フィルタしないため、ここで大引け基準のゲートが要る。
    """
    pre_open = datetime(SESSION.year, SESSION.month, SESSION.day, 9, 0, tzinfo=JST)

    window = available_bars(source=_source([_bar(SESSION)]), code="1234", as_of=pre_open, window_sessions=20)

    assert window.bars == ()
    assert window.last_session is None


def test_session_at_its_close_is_included() -> None:
    at_close = session_close_at(SESSION)

    window = available_bars(source=_source([_bar(SESSION)]), code="1234", as_of=at_close, window_sessions=20)

    assert window.last_session == SESSION


def test_naive_as_of_is_rejected() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        require_aware(datetime(2026, 11, 20, 15, 30))

    with pytest.raises(ValueError, match="timezone-aware"):
        available_bars(
            source=_source([_bar(SESSION)]),
            code="1234",
            as_of=datetime(2026, 11, 20, 15, 30),
            window_sessions=20,
        )


def test_duplicate_sessions_are_collapsed_and_counted() -> None:
    """[MEDIUM] 重複行がカバレッジの分母を水増ししない。"""
    bars = [_bar(SESSION - timedelta(days=i)) for i in range(5)]
    duplicated = [*bars, *bars[:2]]

    window = available_bars(source=_source(duplicated), code="1234", as_of=session_close_at(SESSION), window_sessions=20)

    assert len(window.bars) == 5
    assert window.duplicate_sessions_dropped == 2
    assert len({bar.session_date for bar in window.bars}) == 5


def test_bars_are_sorted_even_if_the_source_is_not() -> None:
    """[LOW] Protocolの昇順は約束にすぎないので、ここで整列を担保する。"""
    sessions = [SESSION - timedelta(days=i) for i in range(6)]
    shuffled = [_bar(s) for s in (sessions[3], sessions[0], sessions[5], sessions[1], sessions[4], sessions[2])]

    window = available_bars(source=_source(shuffled), code="1234", as_of=session_close_at(SESSION), window_sessions=4)

    dates = [bar.session_date for bar in window.bars]
    assert dates == sorted(dates)
    # 整列後の直近4本であること(任意の4本ではない)。
    assert dates == sorted(sessions)[-4:]


def test_staleness_is_measured_against_as_of() -> None:
    old = SESSION - timedelta(days=400)

    window = available_bars(source=_source([_bar(old)]), code="1234", as_of=session_close_at(SESSION), window_sessions=20)

    assert window.last_session == old
    assert window.staleness_days == 400


def test_empty_history_reports_no_staleness_rather_than_zero() -> None:
    window = available_bars(source=StaticPriceHistory({}), code="9999", as_of=session_close_at(SESSION), window_sessions=20)

    assert window.bars == ()
    assert window.staleness_days is None
    assert window.first_session is None
    assert window.last_session is None
