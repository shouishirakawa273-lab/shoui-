"""Strategy定義とライフサイクル状態(ACTIVE/WATCH/DEGRADED/RETIRED)。

Signalの定義(何を選ぶか)とPortfolio Construction(どう組み合わせるか)は別問題として分離する。
Portfolio Constructionのルールは lib/schemas/portfolio_rules.py。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from lib.schemas.base import RecordMeta


class StrategyStatus(StrEnum):
    ACTIVE = "ACTIVE"
    WATCH = "WATCH"
    DEGRADED = "DEGRADED"
    RETIRED = "RETIRED"


@dataclass(kw_only=True, frozen=True)
class RetirementCriterion:
    """例: 「直近12か月Alpha < 0」のような定量的な引退条件。"""

    description: str
    metric: str
    threshold: float
    comparator: str  # "<" / "<=" / ">" / ">=" 等。評価ロジックの実装はPhase2。


@dataclass(kw_only=True, frozen=True)
class Strategy(RecordMeta):
    strategy_id: str
    hypothesis_id: str
    name: str
    description: str
    status: StrategyStatus = StrategyStatus.WATCH
    retirement_criteria: tuple[RetirementCriterion, ...] = field(default_factory=tuple)
    status_reason: str | None = None
