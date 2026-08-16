from __future__ import annotations

from datetime import date, datetime

import pytest
from lib.errors import LookAheadBiasError
from lib.point_in_time import (
    JST,
    PointInTimeRecord,
    assert_no_lookahead,
    is_usable_at,
    session_close_at,
)


def test_session_close_at_is_15_00_jst() -> None:
    close = session_close_at(date(2026, 8, 17))
    assert close == datetime(2026, 8, 17, 15, 0, tzinfo=JST)


def test_record_requires_tz_aware_timestamps() -> None:
    with pytest.raises(ValueError, match="tz-aware"):
        PointInTimeRecord(
            value_date=date(2026, 8, 17),
            published_at=datetime(2026, 8, 17, 15, 30),  # naive
            available_at=datetime(2026, 8, 17, 15, 30, tzinfo=JST),
        )


def test_available_at_before_published_at_is_rejected() -> None:
    with pytest.raises(ValueError, match="available_at"):
        PointInTimeRecord(
            value_date=date(2026, 8, 17),
            published_at=datetime(2026, 8, 17, 15, 30, tzinfo=JST),
            available_at=datetime(2026, 8, 17, 15, 0, tzinfo=JST),
        )


def test_after_hours_disclosure_not_usable_at_same_day_close() -> None:
    """取引時間終了後(15:30)に公表された決算は、同日15:00の大引けでは使えない。"""
    earnings = PointInTimeRecord(
        value_date=date(2026, 8, 17),
        published_at=datetime(2026, 8, 17, 15, 30, tzinfo=JST),
        available_at=datetime(2026, 8, 17, 15, 30, tzinfo=JST),
        label="Q1決算",
    )
    same_day_close = session_close_at(date(2026, 8, 17))
    assert is_usable_at(earnings, same_day_close) is False

    next_day_close = session_close_at(date(2026, 8, 18))
    assert is_usable_at(earnings, next_day_close) is True


def test_assert_no_lookahead_raises_with_violating_record() -> None:
    earnings = PointInTimeRecord(
        value_date=date(2026, 8, 17),
        published_at=datetime(2026, 8, 17, 15, 30, tzinfo=JST),
        available_at=datetime(2026, 8, 17, 15, 30, tzinfo=JST),
        label="Q1決算",
    )
    with pytest.raises(LookAheadBiasError):
        assert_no_lookahead([earnings], session_close_at(date(2026, 8, 17)))


def test_assert_no_lookahead_passes_when_all_available() -> None:
    earnings = PointInTimeRecord(
        value_date=date(2026, 8, 17),
        published_at=datetime(2026, 8, 17, 15, 30, tzinfo=JST),
        available_at=datetime(2026, 8, 17, 15, 30, tzinfo=JST),
        label="Q1決算",
    )
    assert_no_lookahead([earnings], session_close_at(date(2026, 8, 18)))
