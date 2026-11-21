"""会社予想の修正履歴(Step 3)。

`build_revision_histories()` は同一series_idの複数Disclosureを時系列で保持する。
会社予想(`*_current_year_forecast`)のseriesに対してこれを使うと、**いつ・どちら
向きに・何%修正したか**が復元できる。これはStep 4(W4)の入力そのものでもある。

本モジュールは記述のみを行う。上方修正を「良い」と解釈したり、修正幅から売買判断を
導いたりはしない(`RESEARCH_RULES.md`、Knowledge Agentは売買判断をしない)。

PIT: `decision_at` 時点で公表済みのVersionのみを扱う。意味論は呼び出し側が明示的に
指定する(既定なし)。`MARKET_PUBLIC_AT` は「市場参加者がいつ知り得たか」、
`PROVIDER_AVAILABLE_AT` は「このLabのPipelineでいつ取得できたか」であり、両者を
混同しない(`lib/evidence/model.py` の `AvailabilitySemantics`)。

Phase4Aでは `provider_available_at` の `availability_basis` が常に `UNKNOWN` に
なるため、`PROVIDER_AVAILABLE_AT` を指定すると `include_unknown_availability=True`
にしない限り結果が空になる。それは不具合ではなく安全側の既定である。
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from enum import Enum

from lib.evidence.model import AvailabilitySemantics, RevisionHistory
from lib.fundamentals.model import ActualOrForecast, FundamentalMetric, ValueAvailability
from lib.screener.visibility import visible_versions

logger = logging.getLogger(__name__)


class RevisionDirection(Enum):
    """直前Versionに対する向き。`UNKNOWN` は0でもフラットでもない。"""

    UP = "UP"
    DOWN = "DOWN"
    FLAT = "FLAT"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, kw_only=True)
class ForecastRevision:
    """会社予想1回ぶんの改定。初出のVersionも1件として含む(`previous_value=None`)。"""

    published_at: datetime | None
    available_at: datetime
    value: Decimal | None
    previous_value: Decimal | None
    direction: RevisionDirection
    change_ratio: Decimal | None
    """`(value - previous_value) / abs(previous_value)`。

    初出、いずれかが未知、または直前値が0の場合はNone。0除算を避けるためであり、
    「変化なし」を意味しない。
    """
    unknown_reason: str | None = None
    source_version_id: str


@dataclass(frozen=True, kw_only=True)
class ForecastRevisionSeries:
    """1つの予想series(例: 今期営業利益の会社予想)の改定履歴。"""

    series_id: str
    metric_type: str
    accounting_standard: str | None
    decision_at: datetime
    availability_semantics: AvailabilitySemantics
    revisions: tuple[ForecastRevision, ...]

    @property
    def latest(self) -> ForecastRevision | None:
        return self.revisions[-1] if self.revisions else None

    @property
    def revision_count(self) -> int:
        """初出を除いた改定回数。"""
        return max(0, len(self.revisions) - 1)


def _to_decimal(raw: str) -> Decimal | None:
    if not raw:
        return None
    try:
        return Decimal(raw)
    except (InvalidOperation, ValueError):
        return None


def build_forecast_revision_series(
    *,
    revision_histories: Mapping[str, RevisionHistory],
    metrics: Sequence[FundamentalMetric],
    decision_at: datetime,
    availability_semantics: AvailabilitySemantics,
    include_unknown_availability: bool = False,
) -> tuple[ForecastRevisionSeries, ...]:
    """会社予想seriesの改定履歴を組み立てる。

    `metrics` は series_id から metric_type / accounting_standard を引くために使う。
    会社予想(`ActualOrForecast.COMPANY_FORECAST`)のseriesのみを対象とし、実績
    seriesは除外する。

    Raises:
        ValueError: `decision_at` がtz-naiveの場合。
    """
    if decision_at.tzinfo is None:
        raise ValueError(f"decision_at must be timezone-aware: {decision_at!r}")

    forecast_meta: dict[str, FundamentalMetric] = {}
    for metric in metrics:
        if metric.actual_or_forecast is not ActualOrForecast.COMPANY_FORECAST:
            continue
        forecast_meta.setdefault(metric.series_id, metric)

    series_list: list[ForecastRevisionSeries] = []
    for series_id, meta in sorted(forecast_meta.items()):
        history = revision_histories.get(series_id)
        if history is None:
            continue

        versions = visible_versions(
            history,
            decision_at,
            availability_semantics=availability_semantics,
            include_unknown_availability=include_unknown_availability,
        )

        revisions: list[ForecastRevision] = []
        previous: Decimal | None = None
        for version in versions:
            value = _to_decimal(version.value)
            reason: str | None = None

            if previous is None:
                direction = RevisionDirection.UNKNOWN
                change: Decimal | None = None
                reason = "first observed forecast for this series" if value is not None else "forecast value is not numeric"
            elif value is None:
                direction = RevisionDirection.UNKNOWN
                change = None
                reason = "forecast value is not numeric"
            elif value > previous:
                direction = RevisionDirection.UP
                change = None
            elif value < previous:
                direction = RevisionDirection.DOWN
                change = None
            else:
                direction = RevisionDirection.FLAT
                change = Decimal(0)

            if direction in (RevisionDirection.UP, RevisionDirection.DOWN):
                if previous == 0:
                    change = None
                    reason = "previous forecast is zero, ratio undefined"
                else:
                    assert value is not None and previous is not None
                    change = (value - previous) / abs(previous)

            revisions.append(
                ForecastRevision(
                    published_at=version.published_at,
                    available_at=version.available_at,
                    value=value,
                    previous_value=previous,
                    direction=direction,
                    change_ratio=change,
                    unknown_reason=reason,
                    source_version_id=version.source_version_id,
                )
            )
            if value is not None:
                previous = value

        series_list.append(
            ForecastRevisionSeries(
                series_id=series_id,
                metric_type=meta.metric_type,
                accounting_standard=meta.accounting_standard,
                decision_at=decision_at,
                availability_semantics=availability_semantics,
                revisions=tuple(revisions),
            )
        )

    return tuple(series_list)


def present_forecast_metrics(metrics: Sequence[FundamentalMetric]) -> tuple[FundamentalMetric, ...]:
    """値が `PRESENT` の会社予想Metricのみ。欠損を0扱いしないための補助。"""
    return tuple(
        m
        for m in metrics
        if m.actual_or_forecast is ActualOrForecast.COMPANY_FORECAST and m.value_availability is ValueAvailability.PRESENT
    )
