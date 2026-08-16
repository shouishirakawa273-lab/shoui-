"""Point-in-Time データの区別とLook-ahead bias防止。

日付だけでなく時刻レベルで published_at / available_at を区別する。
とくに取引時間終了後に公表された情報は、同日終値時点の decision_at では
利用できないことをコードレベルで強制する(assert_no_lookahead)。
decision_at / execution_at (意思決定側のタイミング)は lib/backtest/engine.py で扱う。
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone

from lib.errors import LookAheadBiasError

# 日本は夏時間を採用していないため固定オフセットで扱う。
JST = timezone(timedelta(hours=9), name="JST")

# 東証の現物取引の大引け(Phase1時点の概算値。取引時間が変わった場合はここを更新する)。
TSE_MARKET_CLOSE = time(15, 0)


def session_close_at(session_date: date) -> datetime:
    """指定した取引日の大引け時刻(JST, tz-aware)を返す。"""
    return datetime.combine(session_date, TSE_MARKET_CLOSE, tzinfo=JST)


@dataclass(frozen=True)
class PointInTimeRecord:
    """ある1つの観測値の、対象時点(value_date)と入手可能性(published_at/available_at)。"""

    value_date: date
    published_at: datetime
    available_at: datetime
    label: str = ""

    def __post_init__(self) -> None:
        if self.published_at.tzinfo is None or self.available_at.tzinfo is None:
            raise ValueError("published_at / available_at はtz-awareである必要があります")
        if self.available_at < self.published_at:
            raise ValueError("available_at は published_at より前にはなりません")


def is_usable_at(record: PointInTimeRecord, decision_at: datetime) -> bool:
    """decision_at時点でこのレコードが利用可能だったかを判定する。"""
    if decision_at.tzinfo is None:
        raise ValueError("decision_at はtz-awareである必要があります")
    return record.available_at <= decision_at


def assert_no_lookahead(records: Iterable[PointInTimeRecord], decision_at: datetime) -> None:
    """decision_at時点で未入手のレコードが1件でもあれば例外にする(黙って除外しない)。"""
    violations = [r for r in records if not is_usable_at(r, decision_at)]
    if violations:
        detail = ", ".join(f"{r.label or r.value_date}(available_at={r.available_at.isoformat()})" for r in violations)
        raise LookAheadBiasError(
            f"decision_at={decision_at.isoformat()} 時点でまだ利用不可能なレコードが{len(violations)}件含まれています: {detail}"
        )
