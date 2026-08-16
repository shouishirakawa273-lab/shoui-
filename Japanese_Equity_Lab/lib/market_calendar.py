"""東証(TSE)の取引時間を集約管理する。

制度変更(取引時間延長等)はこのモジュールだけを更新すればよいようにし、
大引け時刻のハードコードを他モジュールに散在させない。

現時点で反映している制度変更:
- 2024-11-05: 東証現物市場の後場終了が15:00 -> 15:30に延長。

祝日・臨時休場等を考慮した「次の取引日」の解決はPhase1.1のスコープ外(Phase2で
実データの取引カレンダーと連携する)。呼び出し側が休場日を渡した場合の結果は
未定義(将来の取引カレンダー導入時にバリデーションを追加する)。
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
