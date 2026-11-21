"""Step 3 会社予想改定履歴の合成データテスト。実APIには一切接続しない。"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from lib.evidence.model import AvailabilitySemantics, RevisionHistory, SourceVersion
from lib.fundamentals.model import (
    ActualOrForecast,
    ConsolidationScope,
    FiscalYearTarget,
    FundamentalMetric,
    PeriodBasis,
    PeriodType,
    ValueAvailability,
)
from lib.screener.forecast_revisions import RevisionDirection, build_forecast_revision_series

DECISION_AT = datetime(2026, 11, 21, 15, 30, tzinfo=UTC)
SERIES = "7203|operating_profit_current_year_forecast|CURRENT_FISCAL_YEAR|FY|CONSOLIDATED|IFRS"


def _metric(
    metric_id: str,
    *,
    metric_type: str = "operating_profit_current_year_forecast",
    series_id: str = SERIES,
    kind: ActualOrForecast = ActualOrForecast.COMPANY_FORECAST,
) -> FundamentalMetric:
    return FundamentalMetric(
        metric_id=metric_id,
        envelope_id=f"E_{metric_id}",
        series_id=series_id,
        metric_type=metric_type,
        raw_value="0",
        value=Decimal(0),
        value_availability=ValueAvailability.PRESENT,
        actual_or_forecast=kind,
        fiscal_year_target=FiscalYearTarget.CURRENT_FISCAL_YEAR,
        period_type=PeriodType.FY,
        period_basis=PeriodBasis.CUMULATIVE,
        consolidation_scope=ConsolidationScope.CONSOLIDATED,
        accounting_standard="IFRS",
        source_field="FOP",
    )


def _version(vid: str, value: str, month: int) -> SourceVersion:
    published = datetime(2026, month, 1, 15, 0, tzinfo=UTC)
    return SourceVersion(
        source_record_id=SERIES,
        source_version_id=vid,
        value=value,
        available_at=published,
        retrieved_at=DECISION_AT,
        published_at=published,
    )


def _build(*versions: SourceVersion, metrics: list[FundamentalMetric] | None = None):
    histories = {SERIES: RevisionHistory(series_id=SERIES, versions=tuple(versions))}
    supplied = metrics if metrics is not None else [_metric(v.source_version_id) for v in versions]
    return build_forecast_revision_series(
        revision_histories=histories,
        metrics=supplied,
        decision_at=DECISION_AT,
        availability_semantics=AvailabilitySemantics.MARKET_PUBLIC_AT,
    )


def test_upward_revision_is_measured_against_the_previous_forecast() -> None:
    (series,) = _build(_version("v1", "1000", 5), _version("v2", "1200", 8))

    first, second = series.revisions
    assert first.direction is RevisionDirection.UNKNOWN
    assert first.previous_value is None
    assert first.change_ratio is None
    assert "first observed" in (first.unknown_reason or "")

    assert second.direction is RevisionDirection.UP
    assert second.previous_value == Decimal(1000)
    assert second.change_ratio == Decimal("0.2")
    assert series.revision_count == 1


def test_downward_revision_has_negative_ratio() -> None:
    (series,) = _build(_version("v1", "1000", 5), _version("v2", "750", 8))

    _, second = series.revisions
    assert second.direction is RevisionDirection.DOWN
    assert second.change_ratio == Decimal("-0.25")


def test_unchanged_forecast_is_flat_with_zero_ratio() -> None:
    (series,) = _build(_version("v1", "1000", 5), _version("v2", "1000", 8))

    _, second = series.revisions
    assert second.direction is RevisionDirection.FLAT
    assert second.change_ratio == Decimal(0)
    assert series.revision_count == 1


def test_ratio_from_a_zero_base_is_unknown_not_infinite() -> None:
    (series,) = _build(_version("v1", "0", 5), _version("v2", "500", 8))

    _, second = series.revisions
    assert second.direction is RevisionDirection.UP
    assert second.change_ratio is None
    assert "zero" in (second.unknown_reason or "")


def test_negative_base_uses_absolute_denominator() -> None:
    """赤字予想からの改善で符号が反転しないこと。"""
    (series,) = _build(_version("v1", "-200", 5), _version("v2", "-100", 8))

    _, second = series.revisions
    assert second.direction is RevisionDirection.UP
    assert second.change_ratio == Decimal("0.5")


def test_non_numeric_value_is_unknown_and_does_not_become_the_new_base() -> None:
    (series,) = _build(_version("v1", "1000", 5), _version("v2", "", 7), _version("v3", "1100", 9))

    first, second, third = series.revisions
    assert second.value is None
    assert second.direction is RevisionDirection.UNKNOWN
    assert second.change_ratio is None
    # 直前の有効値1000が基準のまま。空値を0として扱わない。
    assert third.previous_value == Decimal(1000)
    assert third.change_ratio == Decimal("0.1")


def test_revisions_published_after_decision_at_are_excluded() -> None:
    later = _version("v3", "9999", 12)
    (series,) = _build(_version("v1", "1000", 5), _version("v2", "1200", 8), later)

    assert [r.source_version_id for r in series.revisions] == ["v1", "v2"]
    assert series.latest is not None
    assert series.latest.value == Decimal(1200)


def test_actual_series_are_not_treated_as_forecasts() -> None:
    metrics = [
        _metric("v1", metric_type="operating_profit", kind=ActualOrForecast.ACTUAL),
        _metric("v2", metric_type="operating_profit", kind=ActualOrForecast.ACTUAL),
    ]

    result = _build(_version("v1", "1000", 5), _version("v2", "1200", 8), metrics=metrics)

    assert result == ()


def test_naive_decision_at_is_rejected() -> None:
    histories = {SERIES: RevisionHistory(series_id=SERIES, versions=(_version("v1", "1000", 5),))}

    with pytest.raises(ValueError, match="timezone-aware"):
        build_forecast_revision_series(
            revision_histories=histories,
            metrics=[_metric("v1")],
            decision_at=datetime(2026, 11, 21, 15, 30),
            availability_semantics=AvailabilitySemantics.MARKET_PUBLIC_AT,
        )
