"""Price/Volume-derived Positioning Metrics(Phase4C Source #1)。

## なぜこれがPhase4C v1の最初のSourceか

Positioning Source候補(信用取引・空売り・投資部門別売買等)のうち、この
Moduleは既存Repositoryに既にある`RawOHLCVBar`/`AdjustedOHLCVBar`
(`lib.schemas.price_data`、J-Quants `/v2/equities/bars/daily`経由で既に
取得済み)から**追加の外部Source統合無しに**決定論的に導出できる、唯一の
候補である(Phase4C要件§7 Candidate A)。新しいExternal APIの仕様を
推測する必要が無いため、Onboarding Riskが最小。

## Derived Fact != Raw Fact

ここで計算する値(売買代金・N日平均出来高)はJ-Quantsが返す生のFieldでは
なく、このModule自身が`close`/`volume`から計算した値である。したがって
`DataLayer.DERIVED`として記録し(`lib.positioning.evidence`参照)、Raw
Provider Fieldであるかのように装わない。算式は決定論的(同じ入力Bar列・
同じParameterなら常に同じ結果)。

## 高度なSignal化はしない

このModuleが計算するのは記述統計(売買代金・移動平均出来高)のみであり、
Short Squeeze Score・Overhang Score・Crowding Score等のInvestment
Signalは一切生成しない(Phase4C要件§21、§19「高度なSignal化はしない」)。

## Adjusted/Unadjusted・Lookback Windowを明示する

- `build_turnover_value_records()`: `RawOHLCVBar`(未調整)から1日単位の
  売買代金(close × volume)を計算する。単日の値であり複数日にまたがる
  比較を含まないため、株式分割による歪みは(単日内では)発生しない。
- `build_volume_moving_average_records()`: `AdjustedOHLCVBar`
  (株式分割調整済み、`lib.schemas.price_data.apply_split_adjustments_
  as_of`/`build_provider_derived_adjusted_bars`経由)を入力に取る
  **ことを設計上要求する**(型で強制、Rawを渡すとVolume/Priceの
  不連続が分割前後で紛れ込むため)。`window`(トレーリング日数)・
  `minimum_periods`(不足時にNoneを返す最小観測日数、既定は`window`と
  同数=満window必須)を明示Parameterとして要求し、暗黙のDefaultで
  歪んだ値を返さない。
"""

from __future__ import annotations

import statistics
from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal

from lib.evidence.model import AvailabilityBasis, ValueAvailability
from lib.market_calendar import session_close_at
from lib.positioning.model import NORMALIZER_VERSION_PRICE_DERIVED, Frequency, PositioningRecord
from lib.schemas.price_data import AdjustedOHLCVBar, RawOHLCVBar

SOURCE_ID = "PRICE_DERIVED"
METRIC_TURNOVER_VALUE = "TURNOVER_VALUE"
METRIC_VOLUME_MOVING_AVERAGE = "VOLUME_MOVING_AVERAGE"


def _series_id(*, entity_code: str, metric_type: str, frequency: Frequency) -> str:
    return f"{entity_code}:{metric_type}:{SOURCE_ID}:{frequency.value}"


def resolve_available_at(record: PositioningRecord) -> tuple[datetime, AvailabilityBasis]:
    """Price/Volume-derived MetricのAvailability(`lib.positioning.normalize.
    build_revision_histories`の`resolve_available_at`引数として渡す)。

    `observation_end`(このMetricが依拠する最終Bar日)のRaw Bar自体が
    利用可能になる時刻として、既存`lib.schemas.price_data`と同じ確立
    済みの規約(`session_close_at`、`BacktestEngine`/`provider_event_
    available_at`が既に採用している基準)を再利用する。東証の大引け時刻
    という制度的なルールからの推定であるため`AvailabilityBasis.INFERRED`
    (公式に確認されたExact Timestampではないが、Unknownでもない)。
    """
    return session_close_at(record.observation_end), AvailabilityBasis.INFERRED


def build_turnover_value_records(
    bars: Sequence[RawOHLCVBar],
    *,
    retrieved_at: datetime,
    raw_snapshot_ref: str | None = None,
) -> list[PositioningRecord]:
    """1日単位の売買代金(close × volume、未調整`RawOHLCVBar`から算出)。

    `close`/`volume`のいずれかが`None`の場合、値を推測で埋めず
    `value_availability=MISSING_OR_UNSPECIFIED`とする(0埋め禁止)。
    """
    if retrieved_at.tzinfo is None:
        raise ValueError("retrieved_at はtz-awareである必要があります")

    records: list[PositioningRecord] = []
    for bar in bars:
        if bar.close is None or bar.volume is None:
            raw_value: str | None = None
            value: Decimal | None = None
            value_availability = ValueAvailability.MISSING_OR_UNSPECIFIED
        else:
            value = Decimal(str(bar.close)) * Decimal(str(bar.volume))
            raw_value = str(value)
            value_availability = ValueAvailability.PRESENT
        records.append(
            PositioningRecord(
                record_id=f"POS_TURNOVER_{bar.code}_{bar.session_date.isoformat()}",
                series_id=_series_id(entity_code=bar.code, metric_type=METRIC_TURNOVER_VALUE, frequency=Frequency.DAILY),
                entity_code=bar.code,
                provider_code=bar.provider_code,
                metric_type=METRIC_TURNOVER_VALUE,
                source_id=SOURCE_ID,
                frequency=Frequency.DAILY,
                observation_start=bar.session_date,
                observation_end=bar.session_date,
                raw_value=raw_value,
                value=value,
                unit="JPY",
                value_availability=value_availability,
                market_public_at=None,
                market_public_at_basis=AvailabilityBasis.UNKNOWN,
                retrieved_at=retrieved_at,
                raw_snapshot_ref=raw_snapshot_ref,
                source_field="close * volume (RawOHLCVBar, unadjusted)",
                normalizer_version=NORMALIZER_VERSION_PRICE_DERIVED,
            )
        )
    return records


def build_volume_moving_average_records(
    bars: Sequence[AdjustedOHLCVBar],
    *,
    window: int,
    retrieved_at: datetime,
    minimum_periods: int | None = None,
    raw_snapshot_ref: str | None = None,
) -> list[PositioningRecord]:
    """トレーリング`window`日の平均出来高(株式分割調整済み`AdjustedOHLCVBar`から算出)。

    `minimum_periods`未満の有効VolumeしかWindow内に無い場合は
    `MISSING_OR_UNSPECIFIED`とする(既定は`window`と同数=満window必須、
    不足時に少ない日数で計算した値を暗黙に返さない)。
    """
    if retrieved_at.tzinfo is None:
        raise ValueError("retrieved_at はtz-awareである必要があります")
    if window < 1:
        raise ValueError(f"window は1以上である必要があります(window={window})")
    effective_minimum_periods = window if minimum_periods is None else minimum_periods
    if effective_minimum_periods < 1 or effective_minimum_periods > window:
        raise ValueError(f"minimum_periods は1以上window({window})以下である必要があります(minimum_periods={minimum_periods})")

    sorted_bars = sorted(bars, key=lambda b: b.session_date)
    metric_type = f"{METRIC_VOLUME_MOVING_AVERAGE}_{window}D"
    records: list[PositioningRecord] = []
    for i, bar in enumerate(sorted_bars):
        window_bars = sorted_bars[max(0, i - window + 1) : i + 1]
        valid_volumes = [b.volume for b in window_bars if b.volume is not None]
        observation_start = window_bars[0].session_date
        observation_end = bar.session_date
        if len(valid_volumes) < effective_minimum_periods:
            raw_value: str | None = None
            value: Decimal | None = None
            value_availability = ValueAvailability.MISSING_OR_UNSPECIFIED
        else:
            mean_volume = statistics.fmean(valid_volumes)
            value = Decimal(str(mean_volume))
            raw_value = str(value)
            value_availability = ValueAvailability.PRESENT
        records.append(
            PositioningRecord(
                record_id=f"POS_VOLMA{window}_{bar.code}_{bar.session_date.isoformat()}",
                series_id=_series_id(entity_code=bar.code, metric_type=metric_type, frequency=Frequency.DAILY),
                entity_code=bar.code,
                provider_code=None,
                metric_type=metric_type,
                source_id=SOURCE_ID,
                frequency=Frequency.DAILY,
                observation_start=observation_start,
                observation_end=observation_end,
                raw_value=raw_value,
                value=value,
                unit="shares",
                value_availability=value_availability,
                market_public_at=None,
                market_public_at_basis=AvailabilityBasis.UNKNOWN,
                retrieved_at=retrieved_at,
                raw_snapshot_ref=raw_snapshot_ref,
                source_field=(
                    f"mean(volume) over trailing {window} sessions "
                    f"(AdjustedOHLCVBar, split-adjusted, minimum_periods={effective_minimum_periods})"
                ),
                normalizer_version=NORMALIZER_VERSION_PRICE_DERIVED,
            )
        )
    return records
