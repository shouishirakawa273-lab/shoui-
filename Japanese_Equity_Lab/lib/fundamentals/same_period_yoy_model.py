"""Same-Period YoY Change: 同一Metric×同一Disclosure Cadence×前年FYの
Actual Fundamentals比較(Stage 3.12、D0086)。

## v1 Scope: `SAME_PERIOD_YOY_CHANGE_RATIO` のみ

Actual実績同士の比較のみ(Company Forecastとの比較は禁止、`lib.valuation.
current_fy_forecast_builder`のScope外領域)。「Growth」等のPositive方向を
暗示する名称は使わない——値がNegativeでも成立するChange Factであり、
「成長率」ではなく「変化率」として扱う(要件v1-2)。

`SAME_PERIOD_YOY_CHANGE_RATIO` = (current cumulative value / prior fiscal
year's same period-type cumulative value) - 1。「割安/割高」同様、
「増収/減収」「改善/悪化」等のInterpretationは一切含まない、単なる比率の
Fact。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

SOURCE_ID = "SAME_PERIOD_YOY_CHANGE_RATIO"
METRIC_SAME_PERIOD_YOY_CHANGE_RATIO = "SAME_PERIOD_YOY_CHANGE_RATIO"

# v1で許可するUnderlying Metric(Actual・Consolidatedのみ、要件v1-1)。
ALLOWED_UNDERLYING_METRIC_TYPES = frozenset({"sales", "operating_profit", "net_profit", "eps"})


@dataclass(kw_only=True, frozen=True)
class SamePeriodYoYChangeRecord:
    """1件のSame-Period YoY Change Derived Fact。

    Float丸めを研究ロジックの基礎にしないため、値・比率はすべて`Decimal`。
    Current/PriorのTargetは、ID文字列からのFree-form Parsingに依存せず、
    `DisclosureEnvelope`のTyped Dates(`current_fiscal_year_start/end`・
    `current_period_start/end`)から直接保持する(要件v1-5/v1-12)。
    """

    entity_code: str
    metric_type: str = METRIC_SAME_PERIOD_YOY_CHANGE_RATIO
    underlying_metric_type: str
    as_of: datetime

    current_value: Decimal
    current_period_type: str
    current_period_start: date
    current_period_end: date
    current_fiscal_year_start: date
    current_fiscal_year_end: date
    current_published_at: datetime
    current_source_version_id: str

    prior_value: Decimal
    prior_period_start: date
    prior_period_end: date
    prior_fiscal_year_start: date
    prior_fiscal_year_end: date
    prior_published_at: datetime
    prior_source_version_id: str

    calculation_expression: str
    change_ratio: Decimal

    accounting_standard: str | None
    consolidation_scope: str
    period_basis: str

    def __post_init__(self) -> None:
        if self.as_of.tzinfo is None:
            raise ValueError("as_of はtz-awareである必要があります")
        if self.current_published_at.tzinfo is None:
            raise ValueError("current_published_at はtz-awareである必要があります")
        if self.prior_published_at.tzinfo is None:
            raise ValueError("prior_published_at はtz-awareである必要があります")
        if self.underlying_metric_type not in ALLOWED_UNDERLYING_METRIC_TYPES:
            raise ValueError(
                f"underlying_metric_type({self.underlying_metric_type!r})はv1で許可された"
                f"{sorted(ALLOWED_UNDERLYING_METRIC_TYPES)}のいずれかである必要があります"
            )


__all__ = [
    "ALLOWED_UNDERLYING_METRIC_TYPES",
    "METRIC_SAME_PERIOD_YOY_CHANGE_RATIO",
    "SOURCE_ID",
    "SamePeriodYoYChangeRecord",
]
