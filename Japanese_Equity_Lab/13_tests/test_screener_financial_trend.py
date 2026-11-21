"""Step 3 実績財務推移の合成データテスト。実APIには一切接続しない。"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from lib.evidence.model import AvailabilitySemantics, RevisionHistory, SourceVersion
from lib.fundamentals.model import (
    ActualOrForecast,
    ConsolidationScope,
    DisclosureEnvelope,
    FiscalYearTarget,
    FundamentalMetric,
    PeriodBasis,
    PeriodType,
    ValueAvailability,
)
from lib.screener.financial_trend import UNMAPPED_METRICS, build_financial_trend

DECISION_AT = datetime(2026, 11, 21, 15, 30, tzinfo=UTC)
CODE = "7203"
SERIES = "7203|sales|CURRENT_FISCAL_YEAR|FY|CONSOLIDATED|IFRS"


def _envelope(eid: str, period_end: date) -> DisclosureEnvelope:
    return DisclosureEnvelope(
        envelope_id=eid,
        provider_code=CODE,
        internal_code=CODE,
        retrieved_at=DECISION_AT,
        current_period_type=PeriodType.FY,
        current_period_end=period_end,
        accounting_standard="IFRS",
    )


def _metric(
    mid: str,
    *,
    series_id: str = SERIES,
    metric_type: str = "sales",
    kind: ActualOrForecast = ActualOrForecast.ACTUAL,
    period_type: PeriodType = PeriodType.FY,
    availability: ValueAvailability = ValueAvailability.PRESENT,
    accounting_standard: str | None = "IFRS",
) -> FundamentalMetric:
    return FundamentalMetric(
        metric_id=mid,
        envelope_id=f"E_{mid}",
        series_id=series_id,
        metric_type=metric_type,
        raw_value="0",
        value=Decimal(0),
        value_availability=availability,
        actual_or_forecast=kind,
        fiscal_year_target=FiscalYearTarget.CURRENT_FISCAL_YEAR,
        period_type=period_type,
        period_basis=PeriodBasis.CUMULATIVE,
        consolidation_scope=ConsolidationScope.CONSOLIDATED,
        accounting_standard=accounting_standard,
        source_field="Sales",
    )


def _version(mid: str, value: str, published: datetime, *, series_id: str = SERIES) -> SourceVersion:
    return SourceVersion(
        source_record_id=series_id,
        source_version_id=mid,
        value=value,
        available_at=published,
        retrieved_at=DECISION_AT,
        published_at=published,
    )


def _build(
    versions: list[SourceVersion],
    metrics: list[FundamentalMetric],
    envelopes: list[DisclosureEnvelope],
    *,
    metric_types: list[str] | None = None,
):
    by_series: dict[str, list[SourceVersion]] = {}
    for v in versions:
        by_series.setdefault(v.source_record_id, []).append(v)
    histories = {sid: RevisionHistory(series_id=sid, versions=tuple(vs)) for sid, vs in by_series.items()}
    return build_financial_trend(
        code=CODE,
        envelopes=envelopes,
        metrics=metrics,
        revision_histories=histories,
        decision_at=DECISION_AT,
        availability_semantics=AvailabilitySemantics.MARKET_PUBLIC_AT,
        metric_types=metric_types or ["sales"],
    )


def test_one_observation_per_fiscal_period_in_ascending_order() -> None:
    periods = [date(2024, 3, 31), date(2025, 3, 31), date(2026, 3, 31)]
    versions = [
        _version("m1", "100", datetime(2024, 5, 10, tzinfo=UTC)),
        _version("m2", "200", datetime(2025, 5, 10, tzinfo=UTC)),
        _version("m3", "300", datetime(2026, 5, 10, tzinfo=UTC)),
    ]
    metrics = [_metric("m1"), _metric("m2"), _metric("m3")]
    envelopes = [_envelope("E_m1", periods[0]), _envelope("E_m2", periods[1]), _envelope("E_m3", periods[2])]

    result = _build(versions, metrics, envelopes)

    (trend,) = result.trends
    assert [o.fiscal_period_end for o in trend.observations] == periods
    assert [o.value for o in trend.observations] == [Decimal(100), Decimal(200), Decimal(300)]
    assert all(o.superseded_count == 0 for o in trend.observations)


def test_restatement_keeps_the_latest_and_counts_the_superseded() -> None:
    period = date(2025, 3, 31)
    versions = [
        _version("m1", "200", datetime(2025, 5, 10, tzinfo=UTC)),
        _version("m2", "190", datetime(2025, 8, 10, tzinfo=UTC)),
    ]
    metrics = [_metric("m1"), _metric("m2")]
    envelopes = [_envelope("E_m1", period), _envelope("E_m2", period)]

    result = _build(versions, metrics, envelopes)

    (trend,) = result.trends
    (observation,) = trend.observations
    assert observation.value == Decimal(190)
    assert observation.superseded_count == 1


def test_disclosures_published_after_decision_at_are_excluded() -> None:
    versions = [
        _version("m1", "100", datetime(2025, 5, 10, tzinfo=UTC)),
        _version("m2", "999", datetime(2026, 12, 10, tzinfo=UTC)),
    ]
    metrics = [_metric("m1"), _metric("m2")]
    envelopes = [_envelope("E_m1", date(2025, 3, 31)), _envelope("E_m2", date(2026, 3, 31))]

    result = _build(versions, metrics, envelopes)

    (trend,) = result.trends
    assert [o.value for o in trend.observations] == [Decimal(100)]


def test_missing_period_is_absent_rather_than_forward_filled() -> None:
    versions = [
        _version("m1", "100", datetime(2024, 5, 10, tzinfo=UTC)),
        _version("m3", "300", datetime(2026, 5, 10, tzinfo=UTC)),
    ]
    metrics = [_metric("m1"), _metric("m3")]
    envelopes = [_envelope("E_m1", date(2024, 3, 31)), _envelope("E_m3", date(2026, 3, 31))]

    result = _build(versions, metrics, envelopes)

    (trend,) = result.trends
    assert [o.fiscal_period_end for o in trend.observations] == [date(2024, 3, 31), date(2026, 3, 31)]


def test_accounting_standard_change_is_kept_as_separate_series() -> None:
    """基準変更で分かれたseriesを黙って1本に畳まない。"""
    other = "7203|sales|CURRENT_FISCAL_YEAR|FY|CONSOLIDATED|UNKNOWN"
    versions = [
        _version("m1", "100", datetime(2024, 5, 10, tzinfo=UTC)),
        _version("m2", "200", datetime(2025, 5, 10, tzinfo=UTC), series_id=other),
    ]
    metrics = [_metric("m1"), _metric("m2", series_id=other, accounting_standard=None)]
    envelopes = [_envelope("E_m1", date(2024, 3, 31)), _envelope("E_m2", date(2025, 3, 31))]

    result = _build(versions, metrics, envelopes)

    assert len(result.trends) == 2
    assert {t.accounting_standard for t in result.trends} == {"IFRS", None}


def test_forecast_and_quarterly_and_absent_values_are_excluded() -> None:
    versions = [
        _version("m1", "100", datetime(2025, 5, 10, tzinfo=UTC)),
        _version("m2", "50", datetime(2025, 8, 10, tzinfo=UTC)),
        _version("m3", "120", datetime(2025, 9, 10, tzinfo=UTC)),
        _version("m4", "130", datetime(2025, 10, 10, tzinfo=UTC)),
    ]
    metrics = [
        _metric("m1"),
        _metric("m2", period_type=PeriodType.Q2),
        _metric("m3", kind=ActualOrForecast.COMPANY_FORECAST),
        _metric("m4", availability=ValueAvailability.MISSING_OR_UNSPECIFIED),
    ]
    envelopes = [_envelope(f"E_m{i}", date(2025, 3, 31)) for i in range(1, 5)]

    result = _build(versions, metrics, envelopes)

    (trend,) = result.trends
    assert [o.value for o in trend.observations] == [Decimal(100)]


def test_unmapped_metrics_are_reported_not_silently_dropped() -> None:
    versions = [_version("m1", "100", datetime(2025, 5, 10, tzinfo=UTC))]
    metrics = [_metric("m1")]
    envelopes = [_envelope("E_m1", date(2025, 3, 31))]

    result = _build(versions, metrics, envelopes, metric_types=["sales", "pbr", "dividend_yield", "roe"])

    assert set(result.unmapped_metrics) == {"pbr", "dividend_yield", "roe"}
    assert all(m in UNMAPPED_METRICS for m in result.unmapped_metrics)
    # 未マッピング指標はtrendを持たない(0で埋めない)。
    assert {t.metric_type for t in result.trends} == {"sales"}


def test_naive_decision_at_is_rejected() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        build_financial_trend(
            code=CODE,
            envelopes=[],
            metrics=[],
            revision_histories={},
            decision_at=datetime(2026, 11, 21, 15, 30),
            availability_semantics=AvailabilitySemantics.MARKET_PUBLIC_AT,
            metric_types=["sales"],
        )
