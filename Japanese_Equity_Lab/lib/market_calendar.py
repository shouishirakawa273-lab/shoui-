"""東証(TSE)の取引時間・取引カレンダーを集約管理する。

制度変更(取引時間延長等)はこのモジュールだけを更新すればよいようにし、
大引け時刻のハードコードを他モジュールに散在させない。

現時点で反映している制度変更:
- 2024-11-05: 東証現物市場の後場終了が15:00 -> 15:30に延長。

「次の取引日」「前の取引日」「取引日か否か」は土日だけで機械的に計算せず、
`TradingCalendar`(実データの取引カレンダーから構築する)で解決する。
祝日・臨時休場データが無い/範囲外の場合は`TradingCalendarResolutionError`を送出し、
勝手に平日扱いで代替しない(Phase2 RESEARCH_RULES.md参照)。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone

# 日本は夏時間を採用していないため固定オフセットで扱う。
JST = timezone(timedelta(hours=9), name="JST")

MARKET_OPEN_TIME = time(9, 0)

_SESSION_EXTENSION_DATE = date(2024, 11, 5)
_LEGACY_MARKET_CLOSE_TIME = time(15, 0)
_CURRENT_MARKET_CLOSE_TIME = time(15, 30)


def market_close_time(session_date: date) -> time:
    """指定した取引日の大引け時刻(制度変更を反映)。"""
    if session_date >= _SESSION_EXTENSION_DATE:
        return _CURRENT_MARKET_CLOSE_TIME
    return _LEGACY_MARKET_CLOSE_TIME


def session_open_at(session_date: date) -> datetime:
    """指定した取引日の始値時刻(JST, tz-aware)。"""
    return datetime.combine(session_date, MARKET_OPEN_TIME, tzinfo=JST)


def session_close_at(session_date: date) -> datetime:
    """指定した取引日の大引け時刻(JST, tz-aware)。"""
    return datetime.combine(session_date, market_close_time(session_date), tzinfo=JST)


@dataclass(frozen=True)
class SessionSchedule:
    """ある取引日の始値・大引け時刻をまとめたもの。"""

    session_date: date
    open_at: datetime
    close_at: datetime


def session_schedule(session_date: date) -> SessionSchedule:
    return SessionSchedule(
        session_date=session_date,
        open_at=session_open_at(session_date),
        close_at=session_close_at(session_date),
    )


class TradingCalendarResolutionError(Exception):
    """取引日か否かをTrading Calendarデータで解決できない場合に送出する。

    土日を除外するだけの機械的な計算では、祝日・臨時休場・年末年始等を正しく
    扱えない。データが無い/範囲外の日付を「平日だから取引日だろう」と
    勝手に扱うことを禁止するためのエラー。
    """


@dataclass(frozen=True)
class TradingCalendar:
    """実データ(J-Quants trading_calendar等)から構築する取引日カレンダー。

    `trading_dates`に含まれる日付のみを取引日として扱う。`range_start`/`range_end`は
    このカレンダーが「解決可能な」範囲を表し、範囲外の問い合わせは
    (取引日か休場日かに関わらず)`TradingCalendarResolutionError`にする
    (データが無い期間を「土日以外は平日として取引日扱い」のように推測しない)。
    """

    trading_dates: frozenset[date]
    range_start: date
    range_end: date

    def __post_init__(self) -> None:
        if self.range_start > self.range_end:
            raise ValueError("range_start は range_end 以前である必要があります")
        out_of_range = [d for d in self.trading_dates if not (self.range_start <= d <= self.range_end)]
        if out_of_range:
            raise ValueError(f"trading_datesにrange外の日付が含まれています: {sorted(out_of_range)[:3]}...")

    def _check_in_range(self, d: date) -> None:
        if not (self.range_start <= d <= self.range_end):
            raise TradingCalendarResolutionError(
                f"{d} はこのTrading Calendarのデータ範囲({self.range_start}〜{self.range_end})外です。"
                "取引日か休場日かを判断できないため、平日等で代替せずエラーにします。"
            )

    def is_trading_session(self, d: date) -> bool:
        self._check_in_range(d)
        return d in self.trading_dates

    def next_trading_session(self, d: date) -> date:
        """dより後の直近の取引日。dの範囲チェックに加え、結果もカレンダー範囲内である必要がある。"""
        self._check_in_range(d)
        candidates = sorted(x for x in self.trading_dates if x > d)
        if not candidates:
            raise TradingCalendarResolutionError(
                f"{d}より後の取引日がTrading Calendarのデータ範囲({self.range_start}〜{self.range_end})内にありません。"
            )
        return candidates[0]

    def previous_trading_session(self, d: date) -> date:
        """dより前の直近の取引日。"""
        self._check_in_range(d)
        candidates = sorted((x for x in self.trading_dates if x < d), reverse=True)
        if not candidates:
            raise TradingCalendarResolutionError(
                f"{d}より前の取引日がTrading Calendarのデータ範囲({self.range_start}〜{self.range_end})内にありません。"
            )
        return candidates[0]

    def nth_next_trading_session(self, d: date, n: int) -> date:
        """dからn営業日後の取引日(n>=1)。休場日を1営業日としてカウントしない。"""
        if n < 1:
            raise ValueError("n は1以上である必要があります")
        current = d
        for _ in range(n):
            current = self.next_trading_session(current)
        return current
