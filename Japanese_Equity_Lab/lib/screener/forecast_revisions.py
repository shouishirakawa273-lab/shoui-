"""会社予想の改定履歴(Step 3)。

**対象決算期で束ねる。series_idでは束ねない。**

`series_id` は `metric_type | fiscal_year_target | current_period_type | scope |
accounting_standard` で構成されるが、`fiscal_year_target` は
`CURRENT_FISCAL_YEAR` のような**相対ラベル**であり絶対年ではない。
`current_period_type` は開示がどの四半期だったかを表す。

この2つを含むため、series_idで束ねると「毎年のQ1開示」が1系列になってしまう。
2026-11-21の実データ確認(トヨタ7203)では、それが**別々の決算期に対する予想の
前年同期比**を「改定」と呼ぶ出力を生んでいた。

正しい改定列は、同一の**絶対的な対象決算期**に対する予想を公表順に並べたもの。
7203のFY2026(2026-03-31期)EPS予想であれば:

    2025-05(FY開示) 237.57 → 2025-08(Q1) 204.09 → 2025-11(Q2) 224.81
    → 2026-02(Q3) 273.91 → 実績 295.25

対象決算期は開示済みのFieldだけから決める(推測しない):

- `fiscal_year_target == CURRENT_FISCAL_YEAR` → `envelope.current_fiscal_year_end`
- `fiscal_year_target == NEXT_FISCAL_YEAR` → `envelope.next_fiscal_year_end`

FY開示時点では当期が終わっているため `*_current_year_forecast` は空で、新年度の
ガイダンスは `*_next_year_forecast` に載る(7203の実データで確認)。上の対応はこれを
そのまま扱えるので、Field名や開示種別から意味を推測する必要がない。

本モジュールは記述のみを行う。上方修正を「良い」と解釈したり、修正幅から売買判断を
導いたりはしない(`RESEARCH_RULES.md`)。

PIT: `decision_at` 時点で見えていたVersionのみを扱う。意味論は呼び出し側が明示的に
指定する(既定なし)。Phase4Aでは `provider_available_at` の `availability_basis` が
常に `UNKNOWN` になるため、`PROVIDER_AVAILABLE_AT` を指定すると
`include_unknown_availability=True` にしない限り結果が空になる。それは不具合では
なく安全側の既定である。
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from enum import Enum

from lib.evidence.model import AvailabilitySemantics, RevisionHistory, SourceVersion
from lib.fundamentals.model import (
    ActualOrForecast,
    DisclosureEnvelope,
    FiscalYearTarget,
    FundamentalMetric,
    PeriodType,
    ValueAvailability,
)
from lib.screener.visibility import visible_versions

logger = logging.getLogger(__name__)

_FORECAST_SUFFIXES = ("_current_year_forecast", "_next_year_forecast")


class RevisionDirection(Enum):
    """直前Versionに対する向き。`UNKNOWN` は0でもフラットでもない。"""

    UP = "UP"
    DOWN = "DOWN"
    FLAT = "FLAT"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, kw_only=True)
class ForecastRevision:
    """ある対象決算期に対する予想の、1回ぶんの公表。

    初出も1件として含む(`previous_value=None`、`direction=UNKNOWN`)。
    """

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
    disclosure_period_type: PeriodType
    """この予想が載った開示の期種別(Q1/Q2/Q3/FY)。年度内のどこで出た改定か。"""
    source_metric_type: str
    """由来Metric名(`*_current_year_forecast` / `*_next_year_forecast`)。"""
    accounting_standard: str | None
    unknown_reason: str | None = None
    source_version_id: str


@dataclass(frozen=True, kw_only=True)
class ForecastRevisionSeries:
    """1つの対象決算期に対する、1指標の改定列。"""

    metric_family: str
    """`_current_year_forecast` / `_next_year_forecast` を外した基底指標名。"""
    target_fiscal_year_end: date | None
    decision_at: datetime
    availability_semantics: AvailabilitySemantics
    revisions: tuple[ForecastRevision, ...]

    @property
    def latest(self) -> ForecastRevision | None:
        return self.revisions[-1] if self.revisions else None

    @property
    def revision_count(self) -> int:
        """初出を除いた公表回数。"""
        return max(0, len(self.revisions) - 1)

    @property
    def accounting_standards(self) -> tuple[str | None, ...]:
        """この列に現れた会計基準。期中に変わっていれば複数になる。"""
        seen: list[str | None] = []
        for revision in self.revisions:
            if revision.accounting_standard not in seen:
                seen.append(revision.accounting_standard)
        return tuple(seen)


def _to_decimal(raw: str) -> Decimal | None:
    if not raw:
        return None
    try:
        return Decimal(raw)
    except (InvalidOperation, ValueError):
        return None


def metric_family(metric_type: str) -> str:
    """`operating_profit_current_year_forecast` → `operating_profit`。"""
    for suffix in _FORECAST_SUFFIXES:
        if metric_type.endswith(suffix):
            return metric_type[: -len(suffix)]
    return metric_type


def target_fiscal_year_end(metric: FundamentalMetric, envelope: DisclosureEnvelope) -> date | None:
    """予想が指す絶対的な決算期末。開示済みFieldのみから決める。

    Envelopeに該当日付が無ければNoneを返す。推測で埋めない。
    """
    if metric.fiscal_year_target is FiscalYearTarget.NEXT_FISCAL_YEAR:
        return envelope.next_fiscal_year_end
    return envelope.current_fiscal_year_end


def build_forecast_revision_series(
    *,
    revision_histories: Mapping[str, RevisionHistory],
    metrics: Sequence[FundamentalMetric],
    envelopes: Sequence[DisclosureEnvelope],
    decision_at: datetime,
    availability_semantics: AvailabilitySemantics,
    include_unknown_availability: bool = False,
) -> tuple[ForecastRevisionSeries, ...]:
    """会社予想を対象決算期ごとに束ね、公表順の改定列にする。

    同一の対象決算期に対する予想は、FY開示の `*_next_year_forecast` と以降の
    Q1〜Q3開示の `*_current_year_forecast` にまたがる。どちらも同じ決算期を指すので
    1本の列にまとめる。

    値が数値でないVersionはUNKNOWNとして列に残すが、次の比較基準にはしない
    (直前の有効値が基準のまま)。空値を0として扱わない。

    Raises:
        ValueError: `decision_at` がtz-naiveの場合。
    """
    if decision_at.tzinfo is None:
        raise ValueError(f"decision_at must be timezone-aware: {decision_at!r}")

    envelopes_by_id = {e.envelope_id: e for e in envelopes}
    forecast_metrics = {
        m.metric_id: m
        for m in metrics
        if m.actual_or_forecast is ActualOrForecast.COMPANY_FORECAST and m.metric_type.endswith(_FORECAST_SUFFIXES)
    }

    # (metric_family, target_fiscal_year_end) -> 可視Version
    buckets: dict[tuple[str, date | None], list[tuple[SourceVersion, FundamentalMetric, DisclosureEnvelope]]] = {}
    for history in revision_histories.values():
        versions = visible_versions(
            history,
            decision_at,
            availability_semantics=availability_semantics,
            include_unknown_availability=include_unknown_availability,
        )
        for version in versions:
            metric = forecast_metrics.get(version.source_version_id)
            if metric is None:
                continue
            envelope = envelopes_by_id.get(metric.envelope_id)
            if envelope is None:
                continue
            key = (metric_family(metric.metric_type), target_fiscal_year_end(metric, envelope))
            buckets.setdefault(key, []).append((version, metric, envelope))

    series_list: list[ForecastRevisionSeries] = []
    for (family, target_fy), entries in buckets.items():
        entries.sort(key=lambda e: (e[0].published_at or e[0].available_at, e[0].source_version_id))

        revisions: list[ForecastRevision] = []
        previous: Decimal | None = None
        for version, metric, envelope in entries:
            value = _to_decimal(version.value)
            reason: str | None = None

            if value is None:
                direction = RevisionDirection.UNKNOWN
                change: Decimal | None = None
                reason = "forecast value is not numeric"
            elif previous is None:
                direction = RevisionDirection.UNKNOWN
                change = None
                reason = "first observed forecast for this fiscal year"
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
                elif value is not None and previous is not None:
                    change = (value - previous) / abs(previous)

            revisions.append(
                ForecastRevision(
                    published_at=version.published_at,
                    available_at=version.available_at,
                    value=value,
                    previous_value=previous,
                    direction=direction,
                    change_ratio=change,
                    disclosure_period_type=envelope.current_period_type,
                    source_metric_type=metric.metric_type,
                    accounting_standard=metric.accounting_standard,
                    unknown_reason=reason,
                    source_version_id=version.source_version_id,
                )
            )
            if value is not None:
                previous = value

        series_list.append(
            ForecastRevisionSeries(
                metric_family=family,
                target_fiscal_year_end=target_fy,
                decision_at=decision_at,
                availability_semantics=availability_semantics,
                revisions=tuple(revisions),
            )
        )

    series_list.sort(key=lambda s: (s.metric_family, s.target_fiscal_year_end is None, s.target_fiscal_year_end or date.min))
    return tuple(series_list)


def present_forecast_metrics(metrics: Sequence[FundamentalMetric]) -> tuple[FundamentalMetric, ...]:
    """値が `PRESENT` の会社予想Metricのみ。欠損を0扱いしないための補助。"""
    return tuple(
        m
        for m in metrics
        if m.actual_or_forecast is ActualOrForecast.COMPANY_FORECAST and m.value_availability is ValueAvailability.PRESENT
    )
