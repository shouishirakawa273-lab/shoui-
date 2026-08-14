"""ドメインモデル定義。

このプロジェクトでは「実績値」と「予想値」を明確に区別して扱う。
予想値には必ずラベル(会社予想/アナリスト予想)と出典・更新日を付与し、
取得できない値は None ではなく明示的な `NOT_AVAILABLE` センチネルで表現する。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum


class Market(StrEnum):
    JP = "JP"
    US = "US"


class ForecastLabel(StrEnum):
    """予想値の出所ラベル。実績値と混同しないよう表示側で必ず併記する。"""

    COMPANY_GUIDANCE = "会社予想"
    ANALYST_CONSENSUS = "アナリスト予想"
    IR_DISCLOSURE = "IR公式発表"


NOT_AVAILABLE = "取得不可"


@dataclass
class ValidationWarning:
    field: str
    message: str
    raw_value: float | None = None


@dataclass
class StockSnapshot:
    """銘柄の実績スナップショット(現在値・指標・直近業績)。"""

    code: str
    market: Market
    name: str | None = None
    currency: str | None = None
    price: float | None = None
    per: float | None = None
    pbr: float | None = None
    roe: float | None = None
    dividend_yield: float | None = None
    market_cap: float | None = None
    week52_high: float | None = None
    week52_low: float | None = None
    sector: str | None = None
    industry: str | None = None
    revenue_ttm: float | None = None
    operating_income_ttm: float | None = None
    net_income_ttm: float | None = None
    fetched_at: datetime = field(default_factory=datetime.now)
    warnings: list[ValidationWarning] = field(default_factory=list)
    source: str = "yfinance"

    def is_missing(self, attr: str) -> bool:
        return getattr(self, attr, None) is None


@dataclass
class ForecastValue:
    """業績予想の単一項目(売上・EPS成長率など)。"""

    metric: str
    value: float | None
    label: ForecastLabel | None
    source: str
    source_url: str | None
    as_of: str | None
    available: bool = True

    @classmethod
    def unavailable(cls, metric: str, reason: str = "") -> ForecastValue:
        return cls(
            metric=metric,
            value=None,
            label=None,
            source=NOT_AVAILABLE,
            source_url=None,
            as_of=reason or None,
            available=False,
        )


@dataclass
class ForecastSnapshot:
    code: str
    market: Market
    values: list[ForecastValue] = field(default_factory=list)
    fetched_at: datetime = field(default_factory=datetime.now)
