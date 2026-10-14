"""Stage 3.9(D0083): `guidance_metric_to_evidence_market_public_at()`のTest。

Company Guidance(Current Fiscal Year Forecastのみ)専用のA系統
(MARKET_PUBLIC_AT)Evidence Converterが、既存Financial Quality Converter
(D0080/D0081)とはContent Format(Forecast Horizon != Disclosure Current
Period)を意図的に共有せず、かつ既存A系統PIT Semanticsを維持することを
確認する。既存`financial_quality_metric_to_evidence_market_public_at()`は
変更していないため、既存`test_fundamentals_financial_quality_evidence.py`
はそのまま維持する。
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from lib.evidence.model import AvailabilityBasis, AvailabilitySemantics, RevisionHistory, SourceVersion, ValueAvailability
from lib.fundamentals.evidence import (
    MARKET_PUBLIC_AT_SOURCE_TYPE,
    UNIT_STATUS_UNVERIFIED,
    guidance_metric_to_evidence_market_public_at,
)
from lib.fundamentals.model import (
    ActualOrForecast,
    ConsolidationScope,
    DisclosureEnvelope,
    FiscalYearTarget,
    FundamentalMetric,
    PeriodBasis,
    PeriodType,
)
from lib.fundamentals.view import fundamentals_as_of

_ENTITY = "7203"
_SERIES = "7203|sales_current_year_forecast|CURRENT_FISCAL_YEAR|2Q|CONSOLIDATED|IFRS"


def _envelope(
    *,
    envelope_id: str = "ENV_TEST_G_1",
    market_public_at: datetime | None,
    retrieved_at: datetime = datetime(2026, 8, 16, tzinfo=UTC),
    current_period_start: date | None = date(2024, 4, 1),
    current_period_end: date | None = date(2024, 9, 30),
    current_fiscal_year_start: date | None = date(2024, 4, 1),
    current_fiscal_year_end: date | None = date(2025, 3, 31),
) -> DisclosureEnvelope:
    return DisclosureEnvelope(
        envelope_id=envelope_id,
        provider_code="72030",
        internal_code=_ENTITY,
        disclosure_number="D1",
        document_type="2QFinancialStatements_Consolidated_IFRS",
        disclosure_date=market_public_at.date() if market_public_at is not None else None,
        disclosure_time=market_public_at.strftime("%H:%M") if market_public_at is not None else None,
        market_public_at=market_public_at,
        retrieved_at=retrieved_at,
        current_period_type=PeriodType.Q2,
        current_period_start=current_period_start,
        current_period_end=current_period_end,
        current_fiscal_year_start=current_fiscal_year_start,
        current_fiscal_year_end=current_fiscal_year_end,
        accounting_standard="IFRS",
    )


def _metric(
    envelope: DisclosureEnvelope,
    *,
    metric_id: str = "MET_TEST_G_1",
    value: str = "46000000000000",
    metric_type: str = "sales_current_year_forecast",
    source_field: str = "FSales",
    actual_or_forecast: ActualOrForecast = ActualOrForecast.COMPANY_FORECAST,
    fiscal_year_target: FiscalYearTarget = FiscalYearTarget.CURRENT_FISCAL_YEAR,
) -> FundamentalMetric:
    return FundamentalMetric(
        metric_id=metric_id,
        envelope_id=envelope.envelope_id,
        series_id=_SERIES,
        metric_type=metric_type,
        raw_value=value,
        value=Decimal(value),
        value_availability=ValueAvailability.PRESENT,
        actual_or_forecast=actual_or_forecast,
        fiscal_year_target=fiscal_year_target,
        period_type=PeriodType.Q2,
        period_basis=PeriodBasis.CUMULATIVE,
        consolidation_scope=ConsolidationScope.CONSOLIDATED,
        accounting_standard="IFRS",
        source_field=source_field,
    )


def _version(
    *, published_at: datetime | None, source_version_id: str = "MET_TEST_G_1", value: str = "46000000000000"
) -> SourceVersion:
    return SourceVersion(
        source_record_id=_SERIES,
        source_version_id=source_version_id,
        value=value,
        available_at=datetime(2026, 8, 16, tzinfo=UTC),
        retrieved_at=datetime(2026, 8, 16, tzinfo=UTC),
        availability_basis=AvailabilityBasis.UNKNOWN,
        published_at=published_at,
    )


# --- Converter Guards(§19) ---


def test_company_forecast_is_accepted() -> None:
    published_at = datetime(2024, 11, 6, 4, 55, tzinfo=UTC)
    envelope = _envelope(market_public_at=published_at)
    metric = _metric(envelope)
    version = _version(published_at=published_at)

    evidence = guidance_metric_to_evidence_market_public_at(version, metric=metric, envelope=envelope, entity_code=_ENTITY)
    assert evidence.evidence_id == "EVID_A_G_MET_TEST_G_1"


def test_actual_metric_is_rejected() -> None:
    published_at = datetime(2024, 11, 6, 4, 55, tzinfo=UTC)
    envelope = _envelope(market_public_at=published_at)
    metric = _metric(envelope, actual_or_forecast=ActualOrForecast.ACTUAL)
    version = _version(published_at=published_at)

    with pytest.raises(ValueError, match="COMPANY_FORECAST"):
        guidance_metric_to_evidence_market_public_at(version, metric=metric, envelope=envelope, entity_code=_ENTITY)


def test_current_fiscal_year_is_accepted() -> None:
    published_at = datetime(2024, 11, 6, 4, 55, tzinfo=UTC)
    envelope = _envelope(market_public_at=published_at)
    metric = _metric(envelope, fiscal_year_target=FiscalYearTarget.CURRENT_FISCAL_YEAR)
    version = _version(published_at=published_at)

    evidence = guidance_metric_to_evidence_market_public_at(version, metric=metric, envelope=envelope, entity_code=_ENTITY)
    assert "fiscal_year_target=CURRENT_FISCAL_YEAR" in evidence.content


def test_next_fiscal_year_is_rejected_in_v1() -> None:
    published_at = datetime(2024, 11, 6, 4, 55, tzinfo=UTC)
    envelope = _envelope(market_public_at=published_at)
    metric = _metric(envelope, fiscal_year_target=FiscalYearTarget.NEXT_FISCAL_YEAR)
    version = _version(published_at=published_at)

    with pytest.raises(ValueError, match="CURRENT_FISCAL_YEAR"):
        guidance_metric_to_evidence_market_public_at(version, metric=metric, envelope=envelope, entity_code=_ENTITY)


def test_published_at_none_is_rejected() -> None:
    envelope = _envelope(market_public_at=None)
    metric = _metric(envelope)
    version = _version(published_at=None)

    with pytest.raises(ValueError, match="UNKNOWN"):
        guidance_metric_to_evidence_market_public_at(version, metric=metric, envelope=envelope, entity_code=_ENTITY)


def test_metric_version_mismatch_is_rejected() -> None:
    envelope = _envelope(market_public_at=datetime(2024, 11, 6, tzinfo=UTC))
    metric = _metric(envelope, metric_id="MET_TEST_G_1")
    mismatched_version = _version(published_at=datetime(2024, 11, 6, tzinfo=UTC), source_version_id="MET_OTHER")

    with pytest.raises(ValueError, match="metric.metric_id"):
        guidance_metric_to_evidence_market_public_at(mismatched_version, metric=metric, envelope=envelope, entity_code=_ENTITY)


def test_metric_envelope_mismatch_is_rejected() -> None:
    envelope_a = _envelope(envelope_id="ENV_A", market_public_at=datetime(2024, 11, 6, tzinfo=UTC))
    envelope_b = _envelope(envelope_id="ENV_B", market_public_at=datetime(2024, 11, 6, tzinfo=UTC))
    metric = _metric(envelope_a)
    version = _version(published_at=datetime(2024, 11, 6, tzinfo=UTC))

    with pytest.raises(ValueError, match="metric.envelope_id"):
        guidance_metric_to_evidence_market_public_at(version, metric=metric, envelope=envelope_b, entity_code=_ENTITY)


def test_source_type_market_public_at_is_preserved() -> None:
    published_at = datetime(2024, 11, 6, 4, 55, tzinfo=UTC)
    envelope = _envelope(market_public_at=published_at)
    metric = _metric(envelope)
    version = _version(published_at=published_at)

    evidence = guidance_metric_to_evidence_market_public_at(version, metric=metric, envelope=envelope, entity_code=_ENTITY)
    assert evidence.source.source_type == MARKET_PUBLIC_AT_SOURCE_TYPE


def test_available_at_equals_published_at() -> None:
    published_at = datetime(2024, 11, 6, 4, 55, tzinfo=UTC)
    envelope = _envelope(market_public_at=published_at)
    metric = _metric(envelope)
    version = _version(published_at=published_at)

    evidence = guidance_metric_to_evidence_market_public_at(version, metric=metric, envelope=envelope, entity_code=_ENTITY)
    assert evidence.source.available_at == published_at
    assert evidence.source.published_at == published_at


def test_actual_or_forecast_appears_explicitly_in_content() -> None:
    published_at = datetime(2024, 11, 6, 4, 55, tzinfo=UTC)
    envelope = _envelope(market_public_at=published_at)
    metric = _metric(envelope)
    version = _version(published_at=published_at)

    evidence = guidance_metric_to_evidence_market_public_at(version, metric=metric, envelope=envelope, entity_code=_ENTITY)
    assert "actual_or_forecast=COMPANY_FORECAST" in evidence.content


def test_fiscal_year_target_appears_explicitly_in_content() -> None:
    published_at = datetime(2024, 11, 6, 4, 55, tzinfo=UTC)
    envelope = _envelope(market_public_at=published_at)
    metric = _metric(envelope)
    version = _version(published_at=published_at)

    evidence = guidance_metric_to_evidence_market_public_at(version, metric=metric, envelope=envelope, entity_code=_ENTITY)
    assert "fiscal_year_target=CURRENT_FISCAL_YEAR" in evidence.content


def test_source_field_is_preserved_in_content() -> None:
    published_at = datetime(2024, 11, 6, 4, 55, tzinfo=UTC)
    envelope = _envelope(market_public_at=published_at)
    metric = _metric(envelope, source_field="FSales")
    version = _version(published_at=published_at)

    evidence = guidance_metric_to_evidence_market_public_at(version, metric=metric, envelope=envelope, entity_code=_ENTITY)
    assert "source_field=FSales" in evidence.content


def test_unit_and_currency_are_not_guessed() -> None:
    published_at = datetime(2024, 11, 6, 4, 55, tzinfo=UTC)
    envelope = _envelope(market_public_at=published_at)
    metric = _metric(envelope)
    version = _version(published_at=published_at)

    evidence = guidance_metric_to_evidence_market_public_at(version, metric=metric, envelope=envelope, entity_code=_ENTITY)
    assert f"unit={UNIT_STATUS_UNVERIFIED}" in evidence.content
    assert f"currency={UNIT_STATUS_UNVERIFIED}" in evidence.content
    for forbidden in ("JPY", "yen", "円"):
        assert forbidden not in evidence.content


# --- Forecast Horizon(§20) ---


def test_2q_disclosure_forecast_uses_current_fiscal_year_start_end() -> None:
    published_at = datetime(2024, 11, 6, 4, 55, tzinfo=UTC)
    envelope = _envelope(
        market_public_at=published_at,
        current_period_start=date(2024, 4, 1),
        current_period_end=date(2024, 9, 30),
        current_fiscal_year_start=date(2024, 4, 1),
        current_fiscal_year_end=date(2025, 3, 31),
    )
    metric = _metric(envelope)
    version = _version(published_at=published_at)

    evidence = guidance_metric_to_evidence_market_public_at(version, metric=metric, envelope=envelope, entity_code=_ENTITY)
    assert "forecast_period=2024-04-01..2025-03-31" in evidence.content


def test_2q_guidance_content_does_not_use_current_period_as_forecast_horizon() -> None:
    """2QのCurrent Period End(2024-09-30)は、FY全体のForecast Horizon
    (2025-03-31)とは異なる。Contentが誤ってCurrent Periodを使っていないことを
    区別できる形で確認する(§2の核心制約)。"""
    published_at = datetime(2024, 11, 6, 4, 55, tzinfo=UTC)
    envelope = _envelope(
        market_public_at=published_at,
        current_period_start=date(2024, 4, 1),
        current_period_end=date(2024, 9, 30),
        current_fiscal_year_start=date(2024, 4, 1),
        current_fiscal_year_end=date(2025, 3, 31),
    )
    metric = _metric(envelope)
    version = _version(published_at=published_at)

    evidence = guidance_metric_to_evidence_market_public_at(version, metric=metric, envelope=envelope, entity_code=_ENTITY)
    assert "forecast_period=2024-04-01..2024-09-30" not in evidence.content
    assert "2024-09-30" not in evidence.content


def test_disclosure_period_type_2q_is_preserved() -> None:
    published_at = datetime(2024, 11, 6, 4, 55, tzinfo=UTC)
    envelope = _envelope(market_public_at=published_at)
    metric = _metric(envelope)
    version = _version(published_at=published_at)

    evidence = guidance_metric_to_evidence_market_public_at(version, metric=metric, envelope=envelope, entity_code=_ENTITY)
    assert "disclosure_period_type=2Q" in evidence.content


def test_forecast_period_end_after_published_at_is_not_rejected() -> None:
    """Forecast Period End(2025-03-31)がpublished_at(2024-11-06)より後でも、
    PIT Rejectionの対象にしない(Forecast Horizon != Evidence Availability、§7)。"""
    published_at = datetime(2024, 11, 6, 4, 55, tzinfo=UTC)
    envelope = _envelope(
        market_public_at=published_at, current_fiscal_year_start=date(2024, 4, 1), current_fiscal_year_end=date(2025, 3, 31)
    )
    metric = _metric(envelope)
    version = _version(published_at=published_at)

    evidence = guidance_metric_to_evidence_market_public_at(version, metric=metric, envelope=envelope, entity_code=_ENTITY)
    assert evidence.source.available_at == published_at


def test_availability_remains_published_at_not_forecast_period_end() -> None:
    published_at = datetime(2024, 11, 6, 4, 55, tzinfo=UTC)
    envelope = _envelope(
        market_public_at=published_at, current_fiscal_year_start=date(2024, 4, 1), current_fiscal_year_end=date(2025, 3, 31)
    )
    metric = _metric(envelope)
    version = _version(published_at=published_at)

    evidence = guidance_metric_to_evidence_market_public_at(version, metric=metric, envelope=envelope, entity_code=_ENTITY)
    assert evidence.value_date is None
    assert evidence.source.available_at == published_at
    assert evidence.is_usable_at(published_at)
    assert not evidence.is_usable_at(published_at.replace(day=5))


# --- Real Selection(A-path、§21) ---


def test_future_guidance_disclosure_excluded_by_market_public_at() -> None:
    published_at = datetime(2024, 11, 6, 4, 55, tzinfo=UTC)
    v = _version(published_at=published_at)
    history = RevisionHistory(series_id=_SERIES, versions=(v,))
    result = fundamentals_as_of(
        {_SERIES: history}, datetime(2024, 11, 1, tzinfo=UTC), availability_semantics=AvailabilitySemantics.MARKET_PUBLIC_AT
    )
    assert result[_SERIES] is None


def test_unknown_published_at_excluded_by_fundamentals_as_of() -> None:
    unknown = _version(published_at=None, source_version_id="V_UNKNOWN")
    history = RevisionHistory(series_id=_SERIES, versions=(unknown,))
    result = fundamentals_as_of(
        {_SERIES: history}, datetime(2026, 1, 1, tzinfo=UTC), availability_semantics=AvailabilitySemantics.MARKET_PUBLIC_AT
    )
    assert result[_SERIES] is None


def test_future_revision_does_not_leak() -> None:
    old = _version(published_at=datetime(2024, 8, 1, tzinfo=UTC), value="46000000000000", source_version_id="V_OLD")
    new = _version(published_at=datetime(2024, 11, 6, tzinfo=UTC), value="46000000000000", source_version_id="V_NEW")
    history = RevisionHistory(series_id=_SERIES, versions=(old, new))

    result = fundamentals_as_of(
        {_SERIES: history},
        datetime(2024, 9, 1, tzinfo=UTC),  # newの公表前
        availability_semantics=AvailabilitySemantics.MARKET_PUBLIC_AT,
    )
    assert result[_SERIES] is old


def test_zero_forecast_remains_valid_present() -> None:
    published_at = datetime(2024, 11, 6, 4, 55, tzinfo=UTC)
    envelope = _envelope(market_public_at=published_at)
    metric = _metric(envelope, value="0", metric_type="operating_profit_current_year_forecast", source_field="FOP")
    version = _version(published_at=published_at, value="0")

    evidence = guidance_metric_to_evidence_market_public_at(version, metric=metric, envelope=envelope, entity_code=_ENTITY)
    assert metric.value == Decimal("0")
    assert metric.value_availability == ValueAvailability.PRESENT
    assert "=0(market_public_at=" in evidence.content


def test_negative_forecast_remains_valid_present() -> None:
    published_at = datetime(2024, 11, 6, 4, 55, tzinfo=UTC)
    envelope = _envelope(market_public_at=published_at)
    metric = _metric(envelope, value="-50000", metric_type="net_profit_current_year_forecast", source_field="FNP")
    version = _version(published_at=published_at, value="-50000")

    evidence = guidance_metric_to_evidence_market_public_at(version, metric=metric, envelope=envelope, entity_code=_ENTITY)
    assert metric.value == Decimal("-50000")
    assert metric.value_availability == ValueAvailability.PRESENT
    assert "=-50000(market_public_at=" in evidence.content
