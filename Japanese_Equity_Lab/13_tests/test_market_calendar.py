from __future__ import annotations

from datetime import date, datetime

import pytest
from lib.market_calendar import (
    JST,
    TradingCalendar,
    TradingCalendarResolutionError,
    session_close_at,
    session_open_at,
)


def test_session_close_before_20241105_is_1500() -> None:
    assert session_close_at(date(2024, 11, 1)) == datetime(2024, 11, 1, 15, 0, tzinfo=JST)
    assert session_close_at(date(2024, 11, 4)) == datetime(2024, 11, 4, 15, 0, tzinfo=JST)


def test_session_close_from_20241105_is_1530() -> None:
    assert session_close_at(date(2024, 11, 5)) == datetime(2024, 11, 5, 15, 30, tzinfo=JST)
    assert session_close_at(date(2026, 8, 17)) == datetime(2026, 8, 17, 15, 30, tzinfo=JST)


def test_session_open_is_0900_regardless_of_close_time_change() -> None:
    assert session_open_at(date(2024, 11, 1)) == datetime(2024, 11, 1, 9, 0, tzinfo=JST)
    assert session_open_at(date(2026, 8, 17)) == datetime(2026, 8, 17, 9, 0, tzinfo=JST)


def _sample_calendar() -> TradingCalendar:
    # 2026-01-01(木、祝日)は休場、2026-01-03(土)は元々週末、2026-01-02(金)は平日営業。
    trading_dates = frozenset(
        {
            date(2026, 1, 2),
            date(2026, 1, 5),
            date(2026, 1, 6),
        }
    )
    return TradingCalendar(trading_dates=trading_dates, range_start=date(2026, 1, 1), range_end=date(2026, 1, 6))


def test_is_trading_session_reflects_holiday_not_just_weekday() -> None:
    calendar = _sample_calendar()
    assert calendar.is_trading_session(date(2026, 1, 1)) is False  # 祝日(平日だが休場)
    assert calendar.is_trading_session(date(2026, 1, 2)) is True


def test_next_trading_session_skips_holiday_gap() -> None:
    calendar = _sample_calendar()
    assert calendar.next_trading_session(date(2026, 1, 2)) == date(2026, 1, 5)  # 1/3,1/4は範囲内だが非取引日


def test_previous_trading_session() -> None:
    calendar = _sample_calendar()
    assert calendar.previous_trading_session(date(2026, 1, 6)) == date(2026, 1, 5)


def test_nth_next_trading_session() -> None:
    calendar = _sample_calendar()
    assert calendar.nth_next_trading_session(date(2026, 1, 2), 2) == date(2026, 1, 6)


def test_out_of_range_date_raises_instead_of_assuming_weekday() -> None:
    """Calendar取得不能(範囲外)の日付を、勝手に平日=取引日として扱わない。"""
    calendar = _sample_calendar()
    with pytest.raises(TradingCalendarResolutionError):
        calendar.is_trading_session(date(2026, 2, 1))


def test_next_trading_session_out_of_range_raises() -> None:
    calendar = _sample_calendar()
    with pytest.raises(TradingCalendarResolutionError):
        calendar.next_trading_session(date(2026, 1, 6))  # 範囲内最後の取引日より後が無い


def test_construction_rejects_trading_dates_outside_declared_range() -> None:
    with pytest.raises(ValueError, match="range外"):
        TradingCalendar(
            trading_dates=frozenset({date(2026, 2, 1)}),
            range_start=date(2026, 1, 1),
            range_end=date(2026, 1, 31),
        )
