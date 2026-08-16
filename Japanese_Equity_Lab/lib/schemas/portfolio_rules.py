"""Signal(何を選ぶか)とPortfolio Construction(どう組み合わせるか)の分離。

Ver.1はPortfolio Optimizationをせず、ルールベースの制約のみを表現する。
"""

from __future__ import annotations

from dataclasses import dataclass

from lib.schemas.base import RecordMeta


@dataclass(kw_only=True, frozen=True)
class PortfolioRules(RecordMeta):
    rules_id: str
    max_position_weight: float
    max_sector_weight: float
    max_theme_weight: float
    minimum_cash: float
    earnings_event_exposure: str  # 例: "決算発表前後N営業日はポジションを持たない"
    liquidity_constraint: str  # 例: "1日平均売買代金のX%以内"
