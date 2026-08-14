"""しきい値フィルタによるスクリーニング。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from core.models import StockSnapshot


class Operator(StrEnum):
    GTE = ">="
    LTE = "<="


@dataclass
class ScreeningRule:
    """1つの指標に対するしきい値フィルタ(以上/以下)。"""

    field: str  # StockSnapshot の属性名 (per, pbr, dividend_yield, market_cap 等)
    operator: Operator
    threshold: float

    def matches(self, snapshot: StockSnapshot) -> bool:
        value = getattr(snapshot, self.field, None)
        if value is None:
            return False  # 値が取得できていない銘柄は「条件不明」として除外する
        if self.operator == Operator.GTE:
            return value >= self.threshold
        return value <= self.threshold


def screen(snapshots: list[StockSnapshot], rules: list[ScreeningRule]) -> list[StockSnapshot]:
    """全ルールを満たすスナップショットのみを返す(AND条件)。"""
    return [s for s in snapshots if all(rule.matches(s) for rule in rules)]
