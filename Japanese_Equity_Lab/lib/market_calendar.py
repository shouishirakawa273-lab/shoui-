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

    def completed_month_end_sessions(self, *, reference_as_of: datetime) -> tuple[date, ...]:
        """`reference_as_of`より前に完了している暦月について、各月の最終取引Sessionを
        古い順に返す(Stage 3.15、Historical Valuation Context Monthly Anchor用)。

        「完了した暦月」の判定はRaw Price Barの並び(最後のBarがある日)からは行わない
        (月後半でPrice Barがtruncateされている場合、それを偽のMonth-End Anchorとして
        扱ってしまうため)。この関数は`trading_dates`ではなくTrading Calendar自身の
        `range_end`(実際にこのCalendarがCoverageを持つ範囲)を根拠に、各月のCalendar
        Month End(例: 2024年10月なら`date(2024, 10, 31)`)が`range_end`以内に収まって
        いる場合のみ、その月を「完了として判定可能」とみなす。収まっていない場合は
        `range_end`が単に短いだけなのか、その月がまだ進行中なのかを推測せず、
        `TradingCalendarResolutionError`でfail closedにする(Silent Inference禁止)。

        `reference_as_of`と同一の暦月は常に除外する(月の途中では、その月自体は
        まだ完了していない——Calendar Coverageの有無に関わらず)。

        取引日が1件も存在しない月(理論上のみ、通常は起こらない)は単にAnchor無しとして
        スキップする(Errorにはしない、休場のみの月自体は取引カレンダーとして正常な状態)。

        既存の`is_trading_session`/`next_trading_session`等とは独立した新規Public API
        だが、`range_start`/`range_end`/`trading_dates`という既存Fieldのみを読むだけで
        新しいCalendar概念・新しいField・新しいImportは一切追加しない(汎用的すぎる
        Calendar Refactorを避ける)。
        """
        if reference_as_of.tzinfo is None:
            raise ValueError("reference_as_of はtz-awareである必要があります")
        reference_date = reference_as_of.date()
        if self.range_start > reference_date:
            return ()

        results: list[date] = []
        year, month = self.range_start.year, self.range_start.month
        while (year, month) < (reference_date.year, reference_date.month):
            month_end = _calendar_month_end(year, month)
            if month_end > self.range_end:
                raise TradingCalendarResolutionError(
                    f"{year}-{month:02d}のCalendar Month End({month_end.isoformat()})がTrading "
                    f"CalendarのCoverage(range_end={self.range_end.isoformat()})を超えています。"
                    "この月が実際に完了しているかを判断できないため、Truncatedな範囲の最後の"
                    "Price/取引日を偽のMonth-End Anchorとして扱わず、fail closedにします。"
                )
            sessions_in_month = sorted(d for d in self.trading_dates if d.year == year and d.month == month)
            if sessions_in_month:
                results.append(sessions_in_month[-1])
            year, month = (year + 1, 1) if month == 12 else (year, month + 1)
        return tuple(results)


def _calendar_month_end(year: int, month: int) -> date:
    """指定した年月の暦上の月末日(例: 2024年2月なら2024-02-29)。取引日か否かは問わない。"""
    if month == 12:
        return date(year, 12, 31)
    return date(year, month + 1, 1) - timedelta(days=1)
