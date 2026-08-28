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


# --- completed_month_end_sessions(Stage 3.15、D0089) ------------------------------------


def _three_month_calendar(*, range_end: date = date(2024, 3, 31)) -> TradingCalendar:
    trading_dates = frozenset(
        {
            date(2024, 1, 4),
            date(2024, 1, 31),
            date(2024, 2, 1),
            date(2024, 2, 29),
            date(2024, 3, 1),
            date(2024, 3, 15),
        }
    )
    return TradingCalendar(trading_dates=trading_dates, range_start=date(2024, 1, 1), range_end=range_end)


def test_completed_month_end_sessions_excludes_reference_own_month() -> None:
    """Current Referenceが月中(2024-03-15)の場合、2024年3月自体はHistorical
    Sampleへ含めない(要件v1 §5条件5)。"""
    calendar = _three_month_calendar()
    result = calendar.completed_month_end_sessions(reference_as_of=datetime(2024, 3, 15, 15, 0, tzinfo=JST))
    assert result == (date(2024, 1, 31), date(2024, 2, 29))


def test_completed_month_end_sessions_picks_actual_max_trading_date_not_raw_bar_guess() -> None:
    calendar = _three_month_calendar(range_end=date(2024, 4, 30))
    result = calendar.completed_month_end_sessions(reference_as_of=datetime(2024, 4, 10, 15, 0, tzinfo=JST))
    assert result == (date(2024, 1, 31), date(2024, 2, 29), date(2024, 3, 15))


def test_completed_month_end_sessions_fails_closed_when_coverage_truncated_mid_month() -> None:
    """Price/Calendar CoverageがMarch月の途中(2024-03-15)で終わっている場合、
    Referenceが4月に進んでも「3月は完了した」と推測しない(要件v1 §6、Silent
    Inference禁止、既存TradingCalendarResolutionErrorを再利用)。"""
    calendar = _three_month_calendar(range_end=date(2024, 3, 15))
    with pytest.raises(TradingCalendarResolutionError):
        calendar.completed_month_end_sessions(reference_as_of=datetime(2024, 4, 10, 15, 0, tzinfo=JST))


def test_completed_month_end_sessions_returns_empty_before_calendar_coverage_starts() -> None:
    calendar = _three_month_calendar()
    result = calendar.completed_month_end_sessions(reference_as_of=datetime(2023, 12, 1, 15, 0, tzinfo=JST))
    assert result == ()


def test_completed_month_end_sessions_requires_tz_aware_reference() -> None:
    calendar = _three_month_calendar()
    with pytest.raises(ValueError, match="tz-aware"):
        calendar.completed_month_end_sessions(reference_as_of=datetime(2024, 3, 15, 15, 0))
