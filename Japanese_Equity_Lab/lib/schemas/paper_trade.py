"""Paper Trade記録。理由は後から書き換えない(frozen=trueの値オブジェクト)。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from lib.schemas.base import RecordMeta


class Signal(StrEnum):
    BUY = "BUY"
    HOLD = "HOLD"
    SELL = "SELL"


@dataclass(kw_only=True, frozen=True)
class PaperTrade(RecordMeta):
    paper_trade_id: str
    hypothesis_id: str
    strategy_id: str
    timestamp: datetime
    ticker: str
    price: float
    signal: Signal
    expected_return: float | None
    expected_excess_return: float | None
    probability: float | None
    confidence: str | None
    reason: str
    counter_argument: str | None
    invalidation_condition: str
    # Shadow Portfolio(False)とActual Portfolio(True、人間が実際に選んだ銘柄)の区別。
    selected_by_human: bool = False
