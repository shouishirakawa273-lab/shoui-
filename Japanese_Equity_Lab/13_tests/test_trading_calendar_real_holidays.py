"""実際の日本の祝日・東証休場日を使ってTradingCalendarの挙動を確認する。

このセッションはJ-Quantsへ疎通できないため、実際の`/markets/trading_calendar`
レスポンスは取得できていない(Phase3A完了報告 参照)。その代わり、広く確認できる
2024年の日本の祝日・年末年始休場という事実を手作業で検証した上でカレンダーを構築し、
「土日だけの機械的な判定ではなく、実際の祝日・休場日を扱えること」を確認する。

このfixtureは网羅的な祝日カレンダーではなく、TradingCalendarのロジックを検証する
ための代表的なサンプルである。本番運用では必ずJ-Quants等の実データから
Trading Calendarを構築すること。
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from lib.market_calendar import JST, TradingCalendar, TradingCalendarResolutionError, session_close_at

# 2024年の祝日・東証休場日(手動で検証した既知の事実)。
_2024_HOLIDAYS = {
    date(2024, 1, 1),  # 元日
    date(2024, 1, 2),  # 東証大納会明けの正月休場
    date(2024, 1, 3),  # 同上
    date(2024, 1, 8),  # 成人の日(1月第2月曜)
    date(2024, 2, 12),  # 建国記念の日 振替休日(2/11が日曜のため)
    date(2024, 3, 20),  # 春分の日
    date(2024, 4, 29),  # 昭和の日
    date(2024, 5, 3),  # 憲法記念日
    date(2024, 5, 6),  # こどもの日 振替休日(5/5が日曜のため)
    date(2024, 7, 15),  # 海の日(7月第3月曜)
    date(2024, 9, 16),  # 敬老の日(9月第3月曜)
    date(2024, 9, 23),  # 秋分の日
    date(2024, 10, 14),  # スポーツの日(10月第2月曜)
    date(2024, 11, 4),  # 文化の日 振替休日(11/3が日曜のため)
    date(2024, 12, 31),  # 東証大納会翌日〜年末休場
}


def _all_days(start: date, end: date) -> list[date]:
    days = []
    current = start
    while current <= end:
        days.append(current)
        current += timedelta(days=1)
    return days


def _build_2024_calendar() -> TradingCalendar:
    start, end = date(2024, 1, 1), date(2024, 12, 31)
    all_days = _all_days(start, end)
    trading_dates = frozenset(d for d in all_days if d.weekday() < 5 and d not in _2024_HOLIDAYS)
    return TradingCalendar(trading_dates=trading_dates, range_start=start, range_end=end)


def test_ordinary_weekday_is_a_trading_session() -> None:
    calendar = _build_2024_calendar()
    assert calendar.is_trading_session(date(2024, 6, 3)) is True  # 2024-06-03は月曜、平日、祝日でもない


def test_weekend_is_not_a_trading_session() -> None:
    calendar = _build_2024_calendar()
    assert calendar.is_trading_session(date(2024, 6, 1)) is False  # 土曜
    assert calendar.is_trading_session(date(2024, 6, 2)) is False  # 日曜


def test_japanese_public_holiday_is_not_a_trading_session_even_on_a_weekday() -> None:
    """土日ではなく「祝日」であることが理由で休場になるケース(機械的な曜日判定では検出できない)。"""
    calendar = _build_2024_calendar()
    assert date(2024, 4, 29).weekday() < 5  # 2024-04-29(昭和の日)は月曜(平日)
    assert calendar.is_trading_session(date(2024, 4, 29)) is False


def test_next_trading_session_skips_golden_week_holiday_cluster() -> None:
    """ゴールデンウィーク(5/3-5/6が休場)を挟んでも、次の取引日を正しく解決する。"""
    calendar = _build_2024_calendar()
    # 5/2(木)の次の取引日は、5/3(祝)・5/4(土)・5/5(日)・5/6(振替休日)を飛ばして5/7(火)。
    assert calendar.next_trading_session(date(2024, 5, 2)) == date(2024, 5, 7)


def test_previous_trading_session_skips_golden_week_holiday_cluster() -> None:
    """ゴールデンウィーク明け(5/7)の前の取引日は、休場日群を飛ばして5/2になる。"""
    calendar = _build_2024_calendar()
    assert calendar.previous_trading_session(date(2024, 5, 7)) == date(2024, 5, 2)


def test_calendar_does_not_assume_weekday_means_trading_session_out_of_range() -> None:
    """範囲外の日付は、平日に見えても「取引日だろう」と推測せず失敗する。"""
    calendar = _build_2024_calendar()
    with pytest.raises(TradingCalendarResolutionError):
        calendar.is_trading_session(date(2025, 6, 2))  # 2025年は範囲外(平日だが判定不能)


def test_session_close_time_transitions_around_2024_11_05() -> None:
    """2024-11-05前後の東証取引時間変更(後場終了 15:00 -> 15:30)を実際の日付で確認する。"""
    day_before = date(2024, 11, 1)  # 2024-11-05より前の直近営業日
    transition_day = date(2024, 11, 5)

    assert session_close_at(day_before).timetz() == session_close_at(day_before).replace(hour=15, minute=0).timetz()
    assert session_close_at(transition_day).timetz() == session_close_at(transition_day).replace(hour=15, minute=30).timetz()
    assert session_close_at(day_before).tzinfo == JST
