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

from lib.evidence.model import Frequency

SOURCE_ID = "LATEST_REPORTED_FY_PER"
METRIC_LATEST_REPORTED_FY_PER = "LATEST_REPORTED_FY_PER"
DENOMINATOR_TYPE_FY_ACTUAL_EPS_CONSOLIDATED = "FY_ACTUAL_EPS_CONSOLIDATED"

# Stage 3.10(D0084): Current Fiscal Year Company Forecast EPS基準のPER。
# 「Forward PER」等の汎用名称は使わない(Consensus Forward EPSではなく、
# 会社自身のCurrent FY Forecast EPSであることを明示するため)。
SOURCE_ID_CURRENT_FY_COMPANY_FORECAST_PER = "CURRENT_FY_COMPANY_FORECAST_PER"
METRIC_CURRENT_FY_COMPANY_FORECAST_PER = "CURRENT_FY_COMPANY_FORECAST_PER"
DENOMINATOR_TYPE_CURRENT_FY_COMPANY_FORECAST_EPS_CONSOLIDATED = "CURRENT_FY_COMPANY_FORECAST_EPS_CONSOLIDATED"


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


@dataclass(kw_only=True, frozen=True)
class CurrentFyCompanyForecastPerRecord:
    """1件のCurrent FY Company Forecast PER Derived Fact(Stage 3.10、D0084)。

    `LatestReportedFyPerRecord`(D0077、Actual FY実績Basis)とはDenominator
    選定・Target Semantics・Corporate Action Windowがいずれも異なるため、
    別Recordとして独立させた(Genericな共通Builderへは早期に統合しない、
    `lib.valuation.current_fy_forecast_builder`Docstring参照)。

    `forecast_period_start`/`forecast_period_end`は開示元の`current_fiscal_
    year_start`/`.current_fiscal_year_end`(その開示のCurrent Period=1Q/2Q/
    3Q等ではない)。`disclosure_period_type`はその予想が「どのDisclosure
    Cadenceで開示されたか」を表すのみで、Forecast Horizonではない
    (`lib.fundamentals.evidence.guidance_metric_to_evidence_market_public_
    at()`と同じ区別、D0083参照)。
    """

    entity_code: str
    metric_type: str = METRIC_CURRENT_FY_COMPANY_FORECAST_PER
    as_of: datetime

    price_date: date
    price_value: Decimal
    price_available_at: datetime

    denominator_type: str
    eps_value: Decimal

    forecast_period_start: date
    forecast_period_end: date
    guidance_published_at: datetime

    source_version_id: str
    source_field: str
    fiscal_year_target: str
    disclosure_period_type: str
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
        if self.guidance_published_at.tzinfo is None:
            raise ValueError("guidance_published_at はtz-awareである必要があります")
        if self.forecast_period_start > self.forecast_period_end:
            raise ValueError(
                f"forecast_period_start({self.forecast_period_start.isoformat()})が"
                f"forecast_period_end({self.forecast_period_end.isoformat()})より後です"
            )


# Stage 3.15(D0089): LATEST_REPORTED_FY_PER_HISTORICAL_CONTEXT。
# D0087(Multi-Year Price Snapshot)+ D0088(PIT Correction)で実測したHistorical
# PER Monthly Anchors分布を、Interpretationを含まないDerived Valuation FACT
# として構築する。「Historical Context」自体は既存LATEST_REPORTED_FY_PERと
# 同じMetric Semantics(選定Close Price ÷ 市場公表済み最新FY実績EPS)を使う
# Observation群の記述統計であり、Forward PERとは混ぜない(Codex Recommendation
# B系: 既存Metric名をそのまま接頭に持つ命名を採用)。
SOURCE_ID_LATEST_REPORTED_FY_PER_HISTORICAL_CONTEXT = "LATEST_REPORTED_FY_PER_HISTORICAL_CONTEXT"
METRIC_LATEST_REPORTED_FY_PER_HISTORICAL_CONTEXT = "LATEST_REPORTED_FY_PER_HISTORICAL_CONTEXT"

# Percentile/Median定義(Codex STATISTICAL_DEFINITION_GAP Finding対応、要件v1
# §10/§11): 外部Statistics Library(numpy/scipy/pandas rank等)の暗黙Methodへ
# 依存せず、定義そのものをMethod名としてRecordへ型で保持する。
PERCENTILE_METHOD_EMPIRICAL_CDF_LE = "EMPIRICAL_CDF_LE"
"""count(historical_per <= current_per) * 100 / sample_count(Decimal専用、
tieは分子へ含む、`<=`はInclusive Boundary)。"""
PERCENTILE_SCALE_PERCENT_0_100 = "PERCENT_0_100"
MEDIAN_METHOD_ORDERED_MIDPOINT = "ORDERED_MIDPOINT"
"""Historical PERをascending sortし、奇数nは中央値そのもの、偶数nは中央2値の
Decimal平均(外部Statistics Libraryの暗黙挙動に依存しない)。"""

# Sample Sufficiency Policy(要件v1 §13): 統計的に12件が十分という主張ではなく、
# 「月次Historical Context EvidenceとしてProduction Evidence化する運用上の
# 最低Sample数」というOperational Guardのみを表す(Codex Sample Sufficiency
# Recommendation Cを踏まえたOperational Minimum)。
MINIMUM_MONTHLY_OBSERVATIONS = 12


class HistoricalContextStatus(StrEnum):
    """Historical Valuation ContextのCompleteness状態(要件v1 §9/§14)。

    v1のBuilder(`lib.valuation.historical_context_builder`)は`PARTIAL`のみを
    生成する——`SUPPORTED`への昇格基準(Window長・Regime数・Source Vintage
    検証状況等)はこのStageでは未定義・未実装であり、Sample数だけを理由に
    機械的に`SUPPORTED`へ格上げしない(D0079/D0087/D0088から継続する原則)。
    """

    PARTIAL = "PARTIAL"
    SUPPORTED = "SUPPORTED"  # v1のBuilderからは到達しない(将来の基準策定待ち)


@dataclass(kw_only=True, frozen=True)
class DenominatorRegimeSummary:
    """Historical Sample内で使われた1つのFY実績EPS Denominator Regime(要件v1 §9)。

    複数のFY Denominator Regime(例: FY2022/3実績・FY2023/3実績・FY2024/3実績)を
    1つのHistorical Distributionへ混在させること自体はLATEST_REPORTED_FY_PERの
    Metric Semantics上正しい(各Historical as_of時点での「市場公表済み最新FY実績
    EPS」をそのまま使うMetricのため)。ただしRegime構成そのものは推測せずType付きで
    保持する(要件v1)。
    """

    fiscal_period_end: date
    eps_value: Decimal
    source_version_id: str
    observation_count: int

    def __post_init__(self) -> None:
        if self.observation_count < 1:
            raise ValueError("observation_count は1以上である必要があります")


@dataclass(kw_only=True, frozen=True)
class LatestReportedFyPerHistoricalContextRecord:
    """LATEST_REPORTED_FY_PER_HISTORICAL_CONTEXTの1件のDerived Fact(要件v1 §8)。

    `LatestReportedFyPerRecord`(D0077、単一as_ofのPER)を30件程度集約した
    「Historical Sample分布 + Current Observation」の記述統計のみを保持する。
    方向性のInterpretation(割安/割高等)は一切含まない。

    `available_at`は、この合成Derived Fact自身が独立したPublication Eventを
    持たないため、寄与した全Parent PER Record(Historical + Current)の
    `available_at`(= `max(price_available_at, published_at)`、D0077/D0084と
    同じ定義)の最大値として`lib.valuation.historical_context_builder`が算出し、
    Fieldとして保持する(Evidence変換時に元のParent Recordへ再アクセスしなくて
    済むようにする、`LatestReportedFyPerRecord.price_available_at`と同じ
    「Builderが計算しRecordへ確定保持する」設計を踏襲)。
    """

    entity_code: str
    metric_type: str = METRIC_LATEST_REPORTED_FY_PER_HISTORICAL_CONTEXT
    as_of: datetime

    historical_sample_start_as_of: datetime
    historical_sample_end_as_of: datetime
    anchor_frequency: Frequency

    sample_count: int
    minimum_sample_count: int

    historical_observation_ids: tuple[str, ...]

    denominator_regimes: tuple[DenominatorRegimeSummary, ...]
    distinct_denominator_regime_count: int

    historical_min: Decimal
    historical_median: Decimal
    historical_max: Decimal
    median_method: str

    current_reference_as_of: datetime
    current_reference_price_date: date
    current_per: Decimal
    current_per_observation_id: str

    percentile_method: str
    percentile_scale: str
    current_percentile: Decimal

    current_minus_historical_median: Decimal

    context_status: HistoricalContextStatus

    attempted_anchor_count: int
    excluded_future_anchor_count: int
    unavailable_denominator_count: int
    corporate_action_excluded_count: int

    available_at: datetime

    def __post_init__(self) -> None:
        for field_name in (
            "as_of",
            "historical_sample_start_as_of",
            "historical_sample_end_as_of",
            "current_reference_as_of",
            "available_at",
        ):
            if getattr(self, field_name).tzinfo is None:
                raise ValueError(f"{field_name} はtz-awareである必要があります")

        if self.sample_count != len(self.historical_observation_ids):
            raise ValueError(
                f"sample_count({self.sample_count})がhistorical_observation_idsの件数"
                f"({len(self.historical_observation_ids)})と一致しません(Dangling Parent Guard)"
            )
        if len(set(self.historical_observation_ids)) != len(self.historical_observation_ids):
            raise ValueError("historical_observation_idsに重複があります(Duplicate Parent Guard)")
        if self.current_per_observation_id in self.historical_observation_ids:
            raise ValueError(
                f"current_per_observation_id({self.current_per_observation_id})がhistorical_observation_ids"
                "へ混入しています(Current Observation Contamination Guard)"
            )
        if self.sample_count < self.minimum_sample_count:
            raise ValueError(
                f"sample_count({self.sample_count})がminimum_sample_count({self.minimum_sample_count})未満です"
                "(Sample Sufficiency Policy違反、この状態のRecordは生成禁止)"
            )
        if self.distinct_denominator_regime_count != len(self.denominator_regimes):
            raise ValueError(
                f"distinct_denominator_regime_count({self.distinct_denominator_regime_count})が"
                f"denominator_regimesの件数({len(self.denominator_regimes)})と一致しません"
            )
        if sum(r.observation_count for r in self.denominator_regimes) != self.sample_count:
            raise ValueError("denominator_regimesのobservation_count合計がsample_countと一致しません")
        if self.available_at > self.current_reference_as_of:
            raise ValueError(
                f"available_at({self.available_at.isoformat()})がcurrent_reference_as_of"
                f"({self.current_reference_as_of.isoformat()})より後です(fail closed)"
            )


__all__ = [
    "DENOMINATOR_TYPE_CURRENT_FY_COMPANY_FORECAST_EPS_CONSOLIDATED",
    "DENOMINATOR_TYPE_FY_ACTUAL_EPS_CONSOLIDATED",
    "MEDIAN_METHOD_ORDERED_MIDPOINT",
    "METRIC_CURRENT_FY_COMPANY_FORECAST_PER",
    "METRIC_LATEST_REPORTED_FY_PER",
    "METRIC_LATEST_REPORTED_FY_PER_HISTORICAL_CONTEXT",
    "MINIMUM_MONTHLY_OBSERVATIONS",
    "PERCENTILE_METHOD_EMPIRICAL_CDF_LE",
    "PERCENTILE_SCALE_PERCENT_0_100",
    "SOURCE_ID",
    "SOURCE_ID_CURRENT_FY_COMPANY_FORECAST_PER",
    "SOURCE_ID_LATEST_REPORTED_FY_PER_HISTORICAL_CONTEXT",
    "CorporateActionBasisStatus",
    "CurrentFyCompanyForecastPerRecord",
    "DenominatorRegimeSummary",
    "HistoricalContextStatus",
    "LatestReportedFyPerHistoricalContextRecord",
    "LatestReportedFyPerRecord",
]
