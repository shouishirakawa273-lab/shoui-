"""実績財務の年次推移(Step 3)。

`decision_at` 時点で公表済みの通期実績を、決算期ごとに1点へまとめて時系列にする。
対象は `lib/fundamentals/normalize.py` が正規化済みの指標のみ(sales / operating_profit
/ ordinary_profit / net_profit / eps / total_assets 等)。

**PBR・配当利回り・ROEは出さない。** `normalize.py` が明記する通り、Share Count関連・
Dividend関連・`ROE` はRaw Payloadには存在するがMetricへ未マッピングである。
未マッピングのFieldを名前から推測して読むことは禁止されている(同モジュール
Docstring)。必要になった場合はsource-onboardingの手順で公式仕様を確認してから
マッピングを足す作業になり、本モジュールの責務ではない。

会計基準の変更等でseries_idが分かれる場合、同一決算期に複数のseriesが存在しうる。
本モジュールはそれらを黙って1つに畳まず、`accounting_standard` ごとに分けて保持する
(どのseriesから来た値かを失わない)。
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from lib.evidence.model import AvailabilitySemantics, RevisionHistory
from lib.fundamentals.model import (
    ActualOrForecast,
    DisclosureEnvelope,
    FundamentalMetric,
    PeriodType,
    ValueAvailability,
)
from lib.screener.visibility import visible_versions

logger = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class AnnualObservation:
    """ある決算期・ある指標の、`decision_at` 時点での最新実績値。"""

    fiscal_period_end: date | None
    value: Decimal | None
    published_at: datetime | None
    source_version_id: str
    superseded_count: int
    """この値に至るまでに観測された、より古いVersionの本数。訂正・再表示の痕跡。"""


@dataclass(frozen=True, kw_only=True)
class MetricTrend:
    """1指標ぶんの年次推移。決算期の昇順。"""

    metric_type: str
    accounting_standard: str | None
    series_id: str
    observations: tuple[AnnualObservation, ...]


@dataclass(frozen=True, kw_only=True)
class FinancialTrend:
    """1銘柄ぶんの実績推移。"""

    code: str
    decision_at: datetime
    availability_semantics: AvailabilitySemantics
    trends: tuple[MetricTrend, ...]
    unmapped_metrics: tuple[str, ...]
    """要求されたが正規化対象外の指標名。空欄にせず明示する。"""


UNMAPPED_METRICS = ("pbr", "dividend_yield", "roe", "shares_outstanding", "book_value_per_share")
"""Raw Payloadには存在するがMetricへ未マッピングの指標。

`lib/fundamentals/normalize.py` のモジュールDocstring「依然未検証」節に対応する。
推測で埋めずUNKNOWNとして扱うため、名前だけを定数として持つ。
"""


def _to_decimal(raw: str) -> Decimal | None:
    if not raw:
        return None
    try:
        return Decimal(raw)
    except (InvalidOperation, ValueError):
        return None


def build_financial_trend(
    *,
    code: str,
    envelopes: Sequence[DisclosureEnvelope],
    metrics: Sequence[FundamentalMetric],
    revision_histories: Mapping[str, RevisionHistory],
    decision_at: datetime,
    availability_semantics: AvailabilitySemantics,
    metric_types: Sequence[str],
    include_unknown_availability: bool = False,
) -> FinancialTrend:
    """通期実績の年次推移を組み立てる。

    同一決算期に複数Versionがある場合(訂正・再表示)、`decision_at` 時点で見えて
    いた最新のものを採り、それ以前の本数を `superseded_count` に残す。前方補完は
    しない。ある決算期にVersionが無ければ、その決算期は結果に現れない。

    Raises:
        ValueError: `decision_at` がtz-naiveの場合。
    """
    if decision_at.tzinfo is None:
        raise ValueError(f"decision_at must be timezone-aware: {decision_at!r}")

    envelopes_by_id = {e.envelope_id: e for e in envelopes}
    wanted = set(metric_types)

    def _eligible(metric: FundamentalMetric) -> bool:
        """通期・実績・値ありの、要求された指標だけを通す。

        series_idは metric_type / fiscal_year_target / period_type / scope /
        accounting_standard の組だが、同一series内にも四半期・予想・欠損の
        Versionが混ざりうる。series単位で選ぶだけでは漏れるため、Version単位でも
        同じ判定をかける。
        """
        return (
            metric.metric_type in wanted
            and metric.actual_or_forecast is ActualOrForecast.ACTUAL
            and metric.period_type is PeriodType.FY
            and metric.value_availability is ValueAvailability.PRESENT
        )

    # series_id -> 代表Metric(metric_type / accounting_standard を引くため)
    series_meta: dict[str, FundamentalMetric] = {}
    for metric in metrics:
        if _eligible(metric):
            series_meta.setdefault(metric.series_id, metric)

    eligible_metric_by_version_id = {m.metric_id: m for m in metrics if _eligible(m)}

    trends: list[MetricTrend] = []
    for series_id, meta in sorted(series_meta.items(), key=lambda kv: (kv[1].metric_type, kv[0])):
        history = revision_histories.get(series_id)
        if history is None:
            continue

        versions = visible_versions(
            history,
            decision_at,
            availability_semantics=availability_semantics,
            include_unknown_availability=include_unknown_availability,
        )

        # 決算期ごとに束ね、各期で最後に見えたVersionを採る。
        by_period: dict[date | None, list] = {}
        for version in versions:
            version_metric = eligible_metric_by_version_id.get(version.source_version_id)
            if version_metric is None:
                # 同一series内の四半期・予想・値なしVersion。採用しない。
                continue
            envelope = envelopes_by_id.get(version_metric.envelope_id)
            period_end = envelope.current_period_end if envelope is not None else None
            by_period.setdefault(period_end, []).append(version)

        observations: list[AnnualObservation] = []
        for period_end, period_versions in by_period.items():
            latest = period_versions[-1]
            observations.append(
                AnnualObservation(
                    fiscal_period_end=period_end,
                    value=_to_decimal(latest.value),
                    published_at=latest.published_at,
                    source_version_id=latest.source_version_id,
                    superseded_count=len(period_versions) - 1,
                )
            )

        observations.sort(key=lambda o: (o.fiscal_period_end is None, o.fiscal_period_end))
        trends.append(
            MetricTrend(
                metric_type=meta.metric_type,
                accounting_standard=meta.accounting_standard,
                series_id=series_id,
                observations=tuple(observations),
            )
        )

    unmapped = tuple(m for m in metric_types if m in UNMAPPED_METRICS)
    if unmapped:
        logger.info("screener: %s are not mapped to metrics and are reported as unavailable", ", ".join(unmapped))

    return FinancialTrend(
        code=code,
        decision_at=decision_at,
        availability_semantics=availability_semantics,
        trends=tuple(trends),
        unmapped_metrics=unmapped,
    )
