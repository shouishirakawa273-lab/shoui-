"""Global Market Record Schema(Phase4E-1): 日本株Researchが外部環境として
参照するGlobal Equity Indices・FX・Government Yields・Commodities・
Volatility Indexを、PIT-safe/timezone-aware/source-aware/reproducibleな
形で表現する。

## Data Foundationまで、Market RegimeやInvestment Signalは作らない

Global Market Observation != Macro Interpretation != Regime != Japanese
Stock Conclusion(Phase4E-1要件§3)。「NASDAQ下落」という事実の記述と、
「日本IT株SELL」という投資判断は別Layerであり、このModuleはObservation
のみを扱う。

## Timezoneが最重要(このPhase固有の新しいRisk)

`lib.market_calendar`は東証(JST)専用に固定Offset(`timezone(timedelta(
hours=9))`)で実装されている——日本は夏時間を採用していないため、これは
JSTに対しては正しいが、**米国・欧州市場ではそのまま再利用できない**
(DST[夏時間]により年内でNY Eastern等のUTC Offsetが変わるため)。Global
Marketの`observation_time`/`market_public_at`は、固定Offsetではなく
Python標準の`zoneinfo`(IANA Timezone Database)を使い、`market_timezone`
(例: `"America/New_York"`)から実際のUTC Offsetを都度解決する。DST遷移日
前後を跨いだ固定Offset代用は禁止する(Phase4E-1要件§10、GLOBAL-003)。

## Series Identity(Price Index != Total Return Index)

Display Name(表示名)だけで同一Seriesと判定しない(Phase4E-1要件§21)。
S&P 500のPrice IndexとTotal Return Indexは別Series(配当込み/含まずで
系統的に異なる)。`index_return_type`/`price_type`/`adjustment_status`
という構造的な区別軸を明示Fieldとして持つ(Macroの`SeasonalAdjustment`
と同じ設計判断——Source固有Field名Mappingではなく、経済的に意味が変わる
構造的区別であるためCommon Modelへ含める)。

## Currencyは第一級

`currency`(ISO通貨Code、例: "USD"、Index Pointsなら`None`)と`unit`を
分離して保持する(Phase4E-1要件§22)。

## Long-form、既存PIT Primitiveを再利用する

`GlobalMarketRecord`はseries × session_date × source単位のLong-form 1
レコード。PIT/Revision管理は`lib.evidence.model.RevisionHistory`/
`SourceVersion`/`AvailabilityBasis`をそのまま再利用し、Global Market
専用の新しいVersioning Primitiveは作らない(Fundamentals/Positioning/
Macroと同一のPrimitive)。

## series_idは呼び出し側の責務(Macro Phase4Dの教訓を踏襲)

`series_id`はSource・`metric_name`・`instrument_category`・
`index_return_type`/`price_type`・`currency`・`frequency`のうち区別
すべき軸を全て一意に含める責務を呼び出し側/将来Adapterが負う
(`MacroRecord`と同じ設計、skeptic-reviewer Finding D0055を踏まえ最初
から明記する)。`GlobalMarketRecord`自体はこれを構造的に強制しない。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from lib.evidence.model import AvailabilityBasis, Frequency, ValueAvailability


class InstrumentCategory(StrEnum):
    """5カテゴリ(Phase4E-1要件§5)。Instrument固有のEconomic Meaningまでは
    表さない(それは`metric_name`/`series_id`の役割)。"""

    EQUITY_INDEX = "EQUITY_INDEX"
    FX = "FX"
    RATE = "RATE"
    COMMODITY = "COMMODITY"
    VOLATILITY_INDEX = "VOLATILITY_INDEX"
    UNKNOWN = "UNKNOWN"


class IndexReturnType(StrEnum):
    """Price Index != Total Return Index != Net Return Index(Phase4E-1
    要件§17)。EQUITY_INDEX以外のInstrumentには適用されないため
    `NOT_APPLICABLE`を使う。"""

    PRICE_RETURN = "PRICE_RETURN"
    TOTAL_RETURN = "TOTAL_RETURN"
    NET_RETURN = "NET_RETURN"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    UNKNOWN = "UNKNOWN"


class PriceType(StrEnum):
    """Spot != Front-month Futures != Continuous Contract(Phase4E-1要件
    §16)。Continuous FuturesはRoll Methodology依存でありRaw Truthとして
    扱わない、という原則をType自体で可視化する。EQUITY_INDEX/FX/RATE/
    VOLATILITY_INDEXには通常適用されないため`NOT_APPLICABLE`を使う。"""

    SPOT = "SPOT"
    FRONT_MONTH_FUTURES = "FRONT_MONTH_FUTURES"
    CONTINUOUS_FUTURES = "CONTINUOUS_FUTURES"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    UNKNOWN = "UNKNOWN"


class AdjustmentStatus(StrEnum):
    """Adjusted != Unadjusted != Provider-transformed(Phase4E-1要件
    §18)。Providerの補正仕様が不明な場合は`UNKNOWN`のまま保持し、推測しない。"""

    ADJUSTED = "ADJUSTED"
    UNADJUSTED = "UNADJUSTED"
    PROVIDER_TRANSFORMED = "PROVIDER_TRANSFORMED"
    UNKNOWN = "UNKNOWN"


@dataclass(kw_only=True, frozen=True)
class GlobalMarketRecord:
    """Global Market Metric 1件の観測値(Long-form)。

    `session_date`はこのObservationが属する取引Session(Instrument自身の
    市場の暦日、日本の暦日とは限らない)。`observation_time`は確認済みの
    実際のTimestamp(tz-aware、`market_timezone`のZoneInfoで構築)のみを
    保持し、Sourceが日付のみしか提供しない場合は`None`のままとする(時刻の
    推測禁止、Phase4E-1要件§11)。

    `market_public_at`は呼び出し側が確認済みの正確なTimestampを渡した
    場合のみ設定する(値が無いのに`market_public_at_basis`だけ確信度を
    高くする矛盾状態は禁止、Macro/Positioning/Company IRで確立した
    Patternと同じ)。
    """

    record_id: str
    series_id: str
    series_code: str | None = None
    exchange: str | None = None
    instrument_category: InstrumentCategory
    index_return_type: IndexReturnType = IndexReturnType.NOT_APPLICABLE
    price_type: PriceType = PriceType.NOT_APPLICABLE
    adjustment_status: AdjustmentStatus = AdjustmentStatus.UNKNOWN
    metric_name: str
    source_id: str
    frequency: Frequency
    session_date: date
    market_timezone: str
    observation_time: datetime | None = None
    raw_value: str | None
    value: Decimal | None
    unit: str | None
    currency: str | None = None
    value_availability: ValueAvailability
    market_public_at: datetime | None = None
    market_public_at_basis: AvailabilityBasis = AvailabilityBasis.UNKNOWN
    retrieved_at: datetime
    raw_snapshot_ref: str | None = None
    provenance_id: str | None = None
    source_field: str | None = None
    normalizer_version: str

    def __post_init__(self) -> None:
        if self.retrieved_at.tzinfo is None:
            raise ValueError("retrieved_at はtz-awareである必要があります")
        if self.observation_time is not None and self.observation_time.tzinfo is None:
            raise ValueError("observation_time はtz-awareである必要があります")
        if self.market_public_at is not None and self.market_public_at.tzinfo is None:
            raise ValueError("market_public_at はtz-awareである必要があります")
        if self.market_public_at is None and self.market_public_at_basis != AvailabilityBasis.UNKNOWN:
            raise ValueError("market_public_atが無いのにmarket_public_at_basisをUNKNOWN以外にはできません")
        if not self.market_timezone:
            raise ValueError("market_timezone は空にできません(推測せず明示的なIANA Timezone名を渡すこと)")
