"""Macro/Economic Record Schema(Phase4D): 日本のMacro/Economic Data(CPI・
GDP・失業率・賃金・政策金利等)を、PIT-safe/revision-aware/reproducibleな形で
表現する。

## Data Foundationまで、Economic Interpretation/Investment Conclusionは作らない

Macro Observation != Economic Interpretation != Market Expectation !=
Investment Conclusion(Phase4D要件§2)。「CPI YoY = X%」という事実の記述と、
「Inflation Pressureが高い」という解釈、「利上げの可能性」という予測、
「銀行株が良い」という投資判断は、それぞれ別Layerであり、このModuleは
最初の1つ(Observation)のみを扱う。

## Series Identity(Entity中心ではなくSeries中心)

Positioning/Fundamentals/DisclosuresがEntity(発行体・銘柄)中心だったのに
対し、MacroはSeries Identity(どの統計・どの系列か)が中心になる
(Phase4D要件§23)。CPI総合・コアCPI・コアコアCPIを混同しない。Display
Name(表示名)だけで同一Seriesと判定せず、Provider公式のSeries Code/Table
Codeがあれば`series_code`として保持する(無ければ`None`のまま、推測しない)。

## Long-form、既存PIT Primitiveを再利用する

`MacroRecord`はseries × reference_period × source単位のLong-form 1
レコードであり、Wide Tableを作らない。PIT/Revision管理は`lib.evidence.
model.RevisionHistory`/`SourceVersion`/`AvailabilityBasis`をそのまま
再利用する(`lib.fundamentals`/`lib.positioning`と同じPrimitive、
Macro専用Versioning機構は作らない、`lib.macro.normalize`参照)。

## Vintage(Preliminary/Revised/Final)はRevisionHistoryで表現する

「1次速報 -> 2次速報 -> 確報」のような複数Versionは、新しいVintage専用
概念を発明せず、既存`SourceVersion`の系列(同一`series_id`に対する複数
Version)としてそのまま表現できる(Phase4D要件§15/§16)。`vintage_label`
(例: "PRELIMINARY"、"FINAL")はSourceが明示的に確認できた場合のみ保持する
自由記述Fieldであり、公開順序だけから推測して埋めてはならない(EVIDENCE-003
と同じ原則、Company IR Phase4B-4で確立したPattern)。

## Reference Period != Availability

`reference_period_start`/`reference_period_end`(この統計が対象とする期間、
例: "2026年7月")と、それが実際に利用可能になった時刻(`market_public_at`/
`SourceVersion.available_at`)は別軸。Quarter終了時点でそのQuarterのGDPが
利用可能とは限らない(Quarter Leakage禁止、Phase4D要件§9/§10)。

## Seasonal Adjustmentは別Metricとして保持する

季節調整値(SA)と原数値(NSA)を自動変換・混同しない(Phase4D要件§18)。

## Source固有semanticsを共通Scoreへ潰さない

`metric_name`(例: "CPI_HEADLINE"、"UNEMPLOYMENT_RATE")はSource固有の
まま保持する。総務省のCPIと別Sourceの類似Seriesを、Field名だけで自動統合
しない(Phase4D要件§24)。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from lib.evidence.model import AvailabilityBasis, Frequency, ValueAvailability


class SeasonalAdjustment(StrEnum):
    """季節調整の有無。原数値(NSA)と季節調整値(SA)を別Metricとして扱う
    (Phase4D要件§18、自動変換しない)。"""

    SEASONALLY_ADJUSTED = "SEASONALLY_ADJUSTED"
    NOT_SEASONALLY_ADJUSTED = "NOT_SEASONALLY_ADJUSTED"
    UNKNOWN = "UNKNOWN"


@dataclass(kw_only=True, frozen=True)
class MacroRecord:
    """Macro/Economic Metric 1件の観測値(Long-form)。

    `market_public_at`は呼び出し側が確認済みの正確なTimestampを渡した
    場合のみ設定する(値が無いのに`market_public_at_basis`だけ確信度を
    高くする矛盾状態は禁止、Company IR/Positioningで確立したPatternと同じ)。
    Date-onlyの公表情報からExact Timestampを推測しない(Phase4D要件§11)。

    `vintage_label`はSourceが明示的に確認できた値(例: 公式文書上の"速報"/
    "改定値"等の表記)のみを保持し、推測しない(初期値`None`)。
    """

    record_id: str
    series_id: str
    series_code: str | None = None
    metric_name: str
    source_id: str
    frequency: Frequency
    reference_period_start: date
    reference_period_end: date
    raw_value: str | None
    value: Decimal | None
    unit: str | None
    seasonal_adjustment: SeasonalAdjustment
    value_availability: ValueAvailability
    vintage_label: str | None = None
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
        if self.market_public_at is not None and self.market_public_at.tzinfo is None:
            raise ValueError("market_public_at はtz-awareである必要があります")
        if self.market_public_at is None and self.market_public_at_basis != AvailabilityBasis.UNKNOWN:
            raise ValueError("market_public_atが無いのにmarket_public_at_basisをUNKNOWN以外にはできません")
        if self.reference_period_start > self.reference_period_end:
            raise ValueError(
                f"record_id={self.record_id}: reference_period_start({self.reference_period_start})が"
                f"reference_period_end({self.reference_period_end})より後です"
            )
