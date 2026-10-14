"""Point-in-Time データの区別とLook-ahead bias防止。

日付だけでなく時刻レベルで published_at / available_at を区別する。
とくに取引時間終了後に公表された情報は、同日終値時点の decision_at では
利用できないことをコードレベルで強制する(assert_no_lookahead)。
市場の取引時間は lib/market_calendar.py に集約する(ここでハードコードしない)。
decision_at / execution_at / information_used_at (意思決定側のタイミング)は
lib/backtest/engine.py で扱う。
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime

from lib.errors import LookAheadBiasError


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
