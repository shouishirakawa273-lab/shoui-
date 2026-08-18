"""Positioning / 需給 Record Schema(Phase4C): 投資家ポジション・信用需給・空売り・
売買主体等をPIT-safe / source-aware / reproducibleな形で表現する。

## Data Foundationまで、Signalは作らない

このModuleは「Raw/Canonical Data -> Point-in-Time safe observation ->
Source-specific normalization -> reusable as_of view」までを扱う。short
squeeze score/overhang score/crowding score等のInvestment Signal化・
BUY/SELL判定はこのModuleの責務ではない(将来Research Hypothesisの領域、
DECISIONS.md D0053以降の議論と同じ「Observation != Investment Conclusion」
原則をPositioning Dataへ適用する)。

## Long-form、既存PIT Primitiveを再利用する

`PositioningRecord`はentity x metric x period x source単位のLong-form
1レコードであり、Wide Tableを作らない。PIT/Revision管理は`lib.evidence.
model.RevisionHistory`/`SourceVersion`/`AvailabilityBasis`をそのまま
再利用する(Fundamentalsと同じPrimitiveであり、Positioning専用の新しい
Versioning機構は作らない、`lib.positioning.normalize`参照)。

## Observation Period != Availability Timestamp

`observation_start`/`observation_end`(このMetricがどの期間を対象とする
観測か)と、それがいつ利用可能になったか(`market_public_at`/
`SourceVersion.available_at`)は別軸であり、期間終了日をそのまま
利用可能時刻として扱わない(Period-end leakage禁止、週次データの週初日
からの利用可能扱い・月次データの月内全期間利用可能扱いのいずれも禁止)。

## metric_typeはSource固有のまま、共通Scoreへ潰さない

信用買残・空売り比率・海外投資家売買代金等を全て`positioning_score`の
ような単一の抽象値へ正規化しない。共通化するのはidentity/time/value/
unit/frequency/provenance/availabilityの構造までであり、Economic
Meaning(`metric_type`の実際の意味)はSource固有のまま保持する。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from lib.evidence.model import AvailabilityBasis, ValueAvailability

NORMALIZER_VERSION_PRICE_DERIVED = "POSITIONING_PRICE_DERIVED_NORMALIZER_V1"


class Frequency(StrEnum):
    """Metricの観測頻度。異なるFrequencyのSeriesを暗黙に混ぜない(Phase4C §17)。

    Weekly ValueをDaily Seriesへforward-fillする処理はこのLayerでは行わない
    (後続Research Layerの責務、Data Foundationでは自動forward-fillしない)。
    """

    DAILY = "DAILY"
    WEEKLY = "WEEKLY"
    MONTHLY = "MONTHLY"
    EVENT_DRIVEN = "EVENT_DRIVEN"
    UNKNOWN = "UNKNOWN"


@dataclass(kw_only=True, frozen=True)
class PositioningRecord:
    """Positioning/需給Metric 1件の観測値(Long-form)。

    `series_id`はRevision管理(`lib.evidence.model.RevisionHistory`)の
    Series Keyであり、同一entity・同一metric_type・同一source_id・同一
    frequencyの組み合わせで構築する(`lib.positioning.normalize`参照)。

    `market_public_at`は呼び出し側が確認済みの正確なTimestampを渡した
    場合のみ設定する(値が無いのに`market_public_at_basis`だけ確信度を
    高くする矛盾状態は禁止、Company IR Phase4B-4で確立したPatternと同じ)。
    """

    record_id: str
    series_id: str
    entity_code: str
    provider_code: str | None = None
    metric_type: str
    source_id: str
    frequency: Frequency
    observation_start: date
    observation_end: date
    raw_value: str | None
    value: Decimal | None
    unit: str | None
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
        if self.market_public_at is not None and self.market_public_at.tzinfo is None:
            raise ValueError("market_public_at はtz-awareである必要があります")
        if self.market_public_at is None and self.market_public_at_basis != AvailabilityBasis.UNKNOWN:
            raise ValueError("market_public_atが無いのにmarket_public_at_basisをUNKNOWN以外にはできません")
        if self.observation_start > self.observation_end:
            raise ValueError(
                f"record_id={self.record_id}: observation_start({self.observation_start})が"
                f"observation_end({self.observation_end})より後です"
            )
