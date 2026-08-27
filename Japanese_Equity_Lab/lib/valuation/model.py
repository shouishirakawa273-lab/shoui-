"""Valuation: Price + Fundamental Denominator -> 決定論的Derived Fact(D0077)。

Valuationは`DataCapability.MARKET_PRICE`単独にも`DataCapability.FUNDAMENTAL`
単独にも属さない。両者を組み合わせて初めて成立するDerived Factであるため、
専用の`DataCapability.VALUATION`(`lib.sources.catalog`)を新設した。

## v1 Scope: `LATEST_REPORTED_FY_PER` のみ

「Trailing PER」という曖昧な名称は使わない。TTM(直近12か月合算)EPSは
今回構築しない(四半期を合算する新しいDerivation Logicが必要になり、
v1のScopeを超える、`DO NOT`参照)。

`LATEST_REPORTED_FY_PER` = 選定Close Price ÷ 市場公表済みの最新FY実績EPS
(会社発表の通期実績値そのまま、四半期累計値ではない)。「割安/割高」等の
Interpretationは一切含まない、単なる比率のFact。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

SOURCE_ID = "LATEST_REPORTED_FY_PER"
METRIC_LATEST_REPORTED_FY_PER = "LATEST_REPORTED_FY_PER"
DENOMINATOR_TYPE_FY_ACTUAL_EPS_CONSOLIDATED = "FY_ACTUAL_EPS_CONSOLIDATED"


class CorporateActionBasisStatus(StrEnum):
    """Price/EPSのShare Basis整合性についての確認状態(要件v1-5)。

    v1では`CONFIRMED_NO_ACTION`のみが実際に`LatestReportedFyPerRecord`へ
    付与される値である。Corporate Action Guardが失敗した場合、`lib.
    valuation.builder.build_latest_reported_fy_per()`はRecordそのものを
    生成しない(`None`を返す、fail closed)ため、`UNAVAILABLE`相当の状態は
    Record化されない——「生成しない」という要件そのものをそのまま体現する。
    """

    CONFIRMED_NO_ACTION = "CONFIRMED_NO_ACTION"


@dataclass(kw_only=True, frozen=True)
class LatestReportedFyPerRecord:
    """1件のLatest Reported FY PER Derived Fact。

    Float丸めを研究ロジックの基礎にしないため、金額・比率はすべて`Decimal`。
    `source_version_id`はAudit Trail用のID参照のみで、対象FY/会計基準等の
    重要Metadataは`fiscal_period_end`/`consolidation_scope`/
    `accounting_standard`として型付きFieldに直接保持する(ID文字列からの
    Free-form Parsingに依存しない、要件v1-4)。
    """

    entity_code: str
    metric_type: str = METRIC_LATEST_REPORTED_FY_PER
    as_of: datetime

    price_date: date
    price_value: Decimal
    price_available_at: datetime

    denominator_type: str
    eps_value: Decimal
    fiscal_period_end: date
    published_at: datetime
    source_version_id: str
    consolidation_scope: str
    accounting_standard: str | None

    calculation_expression: str
    multiple: Decimal

    corporate_action_basis_status: CorporateActionBasisStatus

    def __post_init__(self) -> None:
        if self.as_of.tzinfo is None:
            raise ValueError("as_of はtz-awareである必要があります")
        if self.price_available_at.tzinfo is None:
            raise ValueError("price_available_at はtz-awareである必要があります")
        if self.published_at.tzinfo is None:
            raise ValueError("published_at はtz-awareである必要があります")


__all__ = [
    "DENOMINATOR_TYPE_FY_ACTUAL_EPS_CONSOLIDATED",
    "METRIC_LATEST_REPORTED_FY_PER",
    "SOURCE_ID",
    "CorporateActionBasisStatus",
    "LatestReportedFyPerRecord",
]
