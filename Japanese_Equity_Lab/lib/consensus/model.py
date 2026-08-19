"""Consensus / Expectations Inputs Data Foundation(Phase4E-4): 特定Provider
が特定時点で観測していたAnalyst Consensus/Estimateを、PIT-safe/
vintage-aware/source-aware/provenance-preserving/reproducibleな形で表現
する。

## Consensus != Truth(最重要Concept、Phase4E-4要件§6)

Consensusは以下のいずれでもない:

- 市場参加者全員の期待(Market Price-Implied Expectation)。
- 客観的なTruth・将来の実際の着地値。
- 特定Providerを離れた普遍的な「Analystの見解」。

Consensusは常に「特定Provider(`source_id`)が、特定Analyst Universe
(`analyst_count`、Universeの詳細はProvider固有、§25)を、特定Method
(`statistic_type`)で集計した、特定時点(Vintage)のForecast Observation」
として扱う。Provider AのMeanとProvider BのMeanは、Analyst Universeが
異なれば同じ「Consensus」を意味しない(Phase4E-4要件§29)。

## 6つの別概念(Phase4E-4要件§5)

A. Company Guidance(既存`lib.fundamentals`側、このModuleへ複製しない)
B. Analyst Consensus(このModuleの主対象)
C. Individual Analyst Estimate(v1では扱わない、将来拡張余地のみ残す、§26)
D. Market Price-Implied Expectation(将来Expectations Engine、このRound
   では作らない)
E. Actual Result(既存`lib.fundamentals`側、このModuleへ複製しない)
F. Investment Conclusion(このModuleはObservationまで)

## Vintage(最大のPIT Risk、Phase4E-4要件§11〜13)

FY2027 EPS Consensusが2026-06-01に100、2026-07-01に105、2026-08-01に103
と観測された場合、これらは**別Vintage**である。「現在取得したFY2027
Consensus」を「FY2027当時に利用可能だったConsensus Vintage」として扱う
ことは絶対禁止(Historical Consensus Leakage、Phase4E-4要件§12)。

`RevisionHistory`/`SourceVersion`/`AvailabilityBasis`(`lib.evidence.model`、
既存)をそのまま再利用する(Fundamentals/Positioning/Macro/Global Market
と同一Primitive、Consensus専用Versioning機構は作らない、Phase4E-4要件
§33)。**`Forecast Evolution != Correction`**(Phase4E-4要件§32): 100→105
→103という推移は通常Analystの見解が更新されただけであり、訂正
(Correction/Revision Error Fix)ではない。`SourceVersion.is_correction`
は既定`False`のまま維持し、Sourceが明示的にCorrectionと述べない限り
`True`へ変更しない(既存`lib.macro.normalize`/`lib.positioning.normalize`
と同じ扱い、EVIDENCE-003原則)。

## consensus_as_of の意味は Source-specific(Phase4E-4要件§13)

Providerが返す"As of YYYY-MM-DD"のようなFieldは、Snapshot計算時刻・
Analyst Cutoff時刻・Website表示日・API生成日時のいずれを意味するかが
Source固有であり、統一的な意味を持たない。したがって`provider_stated_
as_of`(生のProvider "as of"値、命名は`lib.consensus.view.consensus_as_of()`
というPIT View Function名との混同を避けるため意図的に区別する)として
そのまま保持するのみとし、これを`provider_available_at`へ自動Mapping
しない(Phase4E-4要件§14)。

## Published Time != Provider Availability != Retrieved Time(既存原則の継続)

`published_at`(Sourceが確認済みの正確なTimestampを渡した場合のみ)・
`provider_available_at`(このLabがこのSource経由で実際に参照可能になった
時刻)・`retrieved_at`(Observed Safe Availability Timestamp、"lower
bound"という曖昧語は使わない、Phase4E-4要件§15)は別概念。`provider_
available_at`が未確認の場合、`market_public_at`/`published_at`への
Unsafe Fallbackは禁止(D0049/D0050と同じ原則)。

## Date-only Timestamp(Phase4E-4要件§16)

Providerが日付のみを返す場合、時刻を推測しない。`provider_stated_as_of`
と同じPatternで、tz-awareな正確なTimestampが無い場合は日付のみを保持する
Fieldは持たず(Consensusでは`provider_stated_as_of`自体をNoneのままにする
——DateだけのProvider "as of"値は、そもそも`published_at`/`provider_
available_at`の代用にならないため、無理にDate専用Fieldを追加しない)。

## Fiscal Period Identity(最重要、Phase4E-4要件§17〜19)

日本株特有の厳密さが必要: Current FY/Next FY/Next-next FYとCalendar Year
を同一視しない(例: 2027年3月期 != Calendar 2027)。`period_type`
(`lib.fundamentals.model.PeriodType`、1Q/2Q/3Q/4Q/5Q/FY/OTHER、既存Enum
をそのまま再利用)で四半期/通期を区別し、`target_period_start`/`target_
period_end`(Explicit Period)と`provider_target_period_id`(Provider
Native識別子、例: "FY1"、"202703")を優先Identityとして保持する。
`forecast_horizon`(Relative Label、CURRENT_FY/NEXT_FY等)は補助情報に
留め、Identityの代わりに使わない(Observation時点により意味が変わる
ため、Phase4E-4要件§19)。`fiscal_year_end`(発行体固有の決算期末日)を
保持し、Calendar Yearとの混同を防ぐ。

## Fundamentals ConsolidationScopeの再利用(Phase4E-4要件§21〜22)

将来Consensus vs Actual FundamentalMetric vs Company Guidanceの比較を
可能にするため、Accounting ScopeはFundamentalsと同じ型(`lib.fundamentals.
model.ConsolidationScope`)を再利用する(独自の重複Enumを作らない)。
Providerが明示しない場合は`None`のまま(「Consolidatedとして扱われて
しまう」誤りを防ぐ、Phase4E-4要件§27「UNKNOWN Accounting Scope Is Not
Consolidated」)。

## adjustment_status(自由記述、専用Enumを作らない理由、skeptic-reviewer Finding反映)

`adjustment_status: str | None`(Phase4E-4要件§22「reported/adjusted/
normalized」候補)は自由記述Fieldとして保持する。`lib.global_market.
model.AdjustmentStatus`(ADJUSTED/UNADJUSTED/PROVIDER_TRANSFORMED)は
一見同じ概念に見えるが、実際にはIndex/Price系列の補正(配当込み/含まず
等)を指す別概念であり、Consensus Estimateの「Reported値か、One-time
Item等を除いたAdjusted/Normalized値か」という区別とは意味が異なる
——名称が似ているという理由だけでGlobal MarketのEnumを転用すると、
異なる概念に同じ型を被せる誤りになる(skeptic-reviewer Finding、
Phase4E-4: 当初この判断・理由をDocstringへ明記していなかった)。Provider
がこの区別を明示しない場合が大半であるため、専用Enumを新設して構造を
強制するより、確認できた場合のみ生の記述を保持する設計とした——将来
複数Providerで共通の区別軸が確認できた場合、専用Enum化を再検討する。

## Statistic Type(Phase4E-4要件§23)

Consensus値は単一Fieldへ潰さない。MEAN/MEDIAN/HIGH/LOW/STANDARD_
DEVIATION/COUNT/OTHER/UNKNOWNを`statistic_type`で明示し、Mean != Median
という区別を型で強制する(Default値を持たせない、呼び出し側が必ず明示)。

## Analyst Count(Phase4E-4要件§24)

`analyst_count`はProviderが明示した場合のみFirst-classで保持する
(`None` = 未提供、0ではない、Phase4E-4要件§24/CONS-024)。Analyst Count
が多い方が信頼できる、という解釈はこのModuleでは行わない。

## Company Guidance / Actual Boundary(Phase4E-4要件§28〜29)

Company GuidanceもActual Resultも既存`lib.fundamentals`側の責務であり、
このModuleへ複製しない。将来Join可能なIdentity(entity/metric/target
period/accounting scope/unit/currency)だけを揃える。

## No Surprise / No Priced-in Inference(Phase4E-4要件§30〜31)

Actual > ConsensusからBEAT/MISS/POSITIVE_SURPRISE等を生成しない。
Consensus水準からPriced-in/Upside Likelyを推測しない。このModuleの
いずれのFunctionもそのような値を生成しない。

## D0057との境界(Phase4E-4要件§43)

Consensus Evidence(`lib.consensus.evidence`)を作る場合も、Publication/
Provider Observation Factまでに留め、Backtest/Decision Engineへ一切
接続しない(Validation Backlog #21は維持したまま)。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from lib.evidence.model import AvailabilityBasis, ValueAvailability
from lib.fundamentals.model import ConsolidationScope, PeriodType

NORMALIZER_VERSION = "CONSENSUS_NORMALIZER_V1"


class StatisticType(StrEnum):
    """Consensus値の集計方法(Phase4E-4要件§23)。Default値を持たせず、呼び出し
    側が必ず明示する(Mean != Medianを型で強制する)。"""

    MEAN = "MEAN"
    MEDIAN = "MEDIAN"
    HIGH = "HIGH"
    LOW = "LOW"
    STANDARD_DEVIATION = "STANDARD_DEVIATION"
    COUNT = "COUNT"
    OTHER = "OTHER"
    UNKNOWN = "UNKNOWN"


class ForecastHorizon(StrEnum):
    """Providerが示すRelative Horizon Label(Phase4E-4要件§19)。Identityの
    代わりには使わない(`target_period_start`/`target_period_end`/
    `provider_target_period_id`を優先する、補助情報に留める)。"""

    CURRENT_QUARTER = "CURRENT_QUARTER"
    NEXT_QUARTER = "NEXT_QUARTER"
    CURRENT_FY = "CURRENT_FY"
    NEXT_FY = "NEXT_FY"
    NEXT_NEXT_FY = "NEXT_NEXT_FY"
    EXPLICIT_PERIOD = "EXPLICIT_PERIOD"
    UNKNOWN = "UNKNOWN"


@dataclass(kw_only=True, frozen=True)
class ConsensusRecord:
    """Analyst Consensus/Estimateの1 Observation(Long-form、1レコード =
    entity x metric x target period x statistic_type x source x vintage)。

    `series_id`はRevision/Vintage管理(`lib.evidence.model.RevisionHistory`)
    のGrouping Keyであり、**`source_id`(Provider)**・entity・
    metric_type・target period・statistic_type・accounting_scope・
    currencyのうち区別すべき軸を全て一意に含める責務を呼び出し側/将来
    Normalizerが負う(Fundamentals/Macro/Global Marketと同じ責務分担、
    Current FY MeanとNext FY Meanを同一Seriesへ潰さないこと、Phase4E-4
    要件§38)。**`source_id`を明示するのは、このModule最大の原則
    「Provider AのMean != Provider BのMean」(Consensus != Truth、
    Phase4E-4要件§6/§29)を`series_id`構築の場面でも徹底するため**
    ——`lib.macro.model.MacroRecord`のDocstringが`series_id`構築責務の
    筆頭にSourceを挙げているのと同じ位置付けである(skeptic-reviewer
    Finding、Phase4E-4: 当初この一覧からSourceが抜けており、Macroの
    前例より弱い記述になっていた)。異なるProviderのVintageを誤って
    同一Seriesへ混ぜるとConsensus != Truthという最重要原則そのものを
    破ることになる(CONS-029/030、`13_tests/test_consensus_pit.py`参照)。
    """

    record_id: str
    series_id: str
    source_id: str
    entity_id: str | None = None  # 正規化されたEntity識別子(Ambiguousな場合はNoneのまま、Fail Closed、§47)
    source_entity_identifier: str  # Providerの生Symbol/Ticker/企業ID(Mapping成否によらず保持)
    metric_type: str  # 例: "REVENUE"/"OPERATING_INCOME"/"NET_INCOME"/"EPS"/"DPS"/"EBITDA"/"FREE_CASH_FLOW"
    statistic_type: StatisticType
    analyst_count: int | None = None
    target_period_start: date | None = None
    target_period_end: date | None = None
    provider_target_period_id: str | None = None
    forecast_horizon: ForecastHorizon = ForecastHorizon.UNKNOWN
    period_type: PeriodType = PeriodType.OTHER
    fiscal_year_end: date | None = None
    accounting_scope: ConsolidationScope | None = None
    accounting_standard: str | None = None
    adjustment_status: str | None = None
    raw_value: str | None
    value: Decimal | None
    unit: str | None = None
    currency: str | None = None
    value_availability: ValueAvailability
    provider_stated_as_of: datetime | None = None
    published_at: datetime | None = None
    published_at_basis: AvailabilityBasis = AvailabilityBasis.UNKNOWN
    provider_available_at: datetime | None = None
    provider_available_at_basis: AvailabilityBasis = AvailabilityBasis.UNKNOWN
    retrieved_at: datetime
    raw_snapshot_ref: str | None = None
    source_field: str | None = None
    provenance_id: str | None = None
    normalizer_version: str = NORMALIZER_VERSION

    def __post_init__(self) -> None:
        if not self.record_id:
            raise ValueError("record_id は空にできません")
        if not self.series_id:
            raise ValueError("series_id は空にできません")
        if not self.source_id:
            raise ValueError("source_id は空にできません")
        if not self.source_entity_identifier:
            raise ValueError("source_entity_identifier は空にできません")
        if self.retrieved_at.tzinfo is None:
            raise ValueError("retrieved_at はtz-awareである必要があります")
        if self.provider_stated_as_of is not None and self.provider_stated_as_of.tzinfo is None:
            raise ValueError("provider_stated_as_of はtz-awareである必要があります(日付のみの場合はNoneのままにすること)")
        if self.published_at is not None and self.published_at.tzinfo is None:
            raise ValueError("published_at はtz-awareである必要があります")
        if self.published_at is None and self.published_at_basis != AvailabilityBasis.UNKNOWN:
            raise ValueError("published_atが無いのにpublished_at_basisをUNKNOWN以外にはできません")
        if self.provider_available_at is not None and self.provider_available_at.tzinfo is None:
            raise ValueError("provider_available_at はtz-awareである必要があります")
        if self.provider_available_at is None and self.provider_available_at_basis != AvailabilityBasis.UNKNOWN:
            raise ValueError("provider_available_atが無いのにprovider_available_at_basisをUNKNOWN以外にはできません")
        if (
            self.target_period_start is not None
            and self.target_period_end is not None
            and self.target_period_start > self.target_period_end
        ):
            raise ValueError("target_period_start は target_period_end より後にはできません")
        if self.analyst_count is not None and self.analyst_count < 0:
            raise ValueError("analyst_count は0以上である必要があります")


__all__ = [
    "NORMALIZER_VERSION",
    "ConsensusRecord",
    "ForecastHorizon",
    "StatisticType",
]
