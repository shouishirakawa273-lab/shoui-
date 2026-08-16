from __future__ import annotations

from datetime import date, datetime

from lib.market_calendar import JST, session_close_at, session_open_at


def test_session_close_before_20241105_is_1500() -> None:
    assert session_close_at(date(2024, 11, 1)) == datetime(2024, 11, 1, 15, 0, tzinfo=JST)
    assert session_close_at(date(2024, 11, 4)) == datetime(2024, 11, 4, 15, 0, tzinfo=JST)


def test_session_close_from_20241105_is_1530() -> None:
    assert session_close_at(date(2024, 11, 5)) == datetime(2024, 11, 5, 15, 30, tzinfo=JST)
    assert session_close_at(date(2026, 8, 17)) == datetime(2026, 8, 17, 15, 30, tzinfo=JST)


def test_session_open_is_0900_regardless_of_close_time_change() -> None:
    assert session_open_at(date(2024, 11, 1)) == datetime(2024, 11, 1, 9, 0, tzinfo=JST)
    assert session_open_at(date(2026, 8, 17)) == datetime(2026, 8, 17, 9, 0, tzinfo=JST)
