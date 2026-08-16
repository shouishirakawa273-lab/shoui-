"""Phase4A(D0043): Fundamental Record Schema(DisclosureEnvelope/FundamentalMetric)のテスト。"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from lib.evidence.model import AvailabilityBasis, ValueAvailability
from lib.fundamentals.model import ActualOrForecast, ConsolidationScope, DisclosureEnvelope, FiscalYearTarget, PeriodType


def _envelope(**overrides: object) -> DisclosureEnvelope:
    defaults: dict[str, object] = dict(
        envelope_id="ENV_1",
        provider_code="72030",
        internal_code="7203",
        retrieved_at=datetime(2024, 1, 1, tzinfo=UTC),
    )
    defaults.update(overrides)
    return DisclosureEnvelope(**defaults)  # type: ignore[arg-type]


def test_disclosure_envelope_requires_tz_aware_retrieved_at() -> None:
    with pytest.raises(ValueError, match="tz-aware"):
        DisclosureEnvelope(envelope_id="ENV_1", provider_code="72030", internal_code="7203", retrieved_at=datetime(2024, 1, 1))


def test_disclosure_envelope_requires_tz_aware_market_public_at() -> None:
    with pytest.raises(ValueError, match="tz-aware"):
        _envelope(market_public_at=datetime(2024, 1, 1))


def test_disclosure_envelope_defaults_are_conservative() -> None:
    envelope = _envelope()
    assert envelope.market_public_at is None
    assert envelope.market_public_at_basis == AvailabilityBasis.UNKNOWN
    assert envelope.current_period_type == PeriodType.OTHER
    assert envelope.canonical_entity_id is None
    assert envelope.accounting_standard is None


def test_period_type_covers_all_official_values() -> None:
    """公式仕様上CurPerTypeは1Q/2Q/3Q/4Q/5Q/FYを取りうる(1Q/2Q/3Q/FYに固定しない)。"""
    assert {PeriodType.Q1, PeriodType.Q2, PeriodType.Q3, PeriodType.Q4, PeriodType.Q5, PeriodType.FY}.issubset(set(PeriodType))
    assert PeriodType.OTHER in set(PeriodType)


def test_actual_and_forecast_are_distinct_enum_members() -> None:
    assert ActualOrForecast.ACTUAL != ActualOrForecast.COMPANY_FORECAST


def test_current_and_next_fiscal_year_are_distinct_enum_members() -> None:
    assert FiscalYearTarget.CURRENT_FISCAL_YEAR != FiscalYearTarget.NEXT_FISCAL_YEAR


def test_consolidated_and_non_consolidated_are_distinct_enum_members() -> None:
    assert ConsolidationScope.CONSOLIDATED != ConsolidationScope.NON_CONSOLIDATED


def test_value_availability_has_no_not_yet_available_member() -> None:
    """NOT_YET_AVAILABLEはMetric Valueの属性ではなく、As-of Query Outcome側で扱う
    (D0043 Additional Corrections)。Stored Value StateのEnumには含めない。"""
    assert not hasattr(ValueAvailability, "NOT_YET_AVAILABLE")
    assert {
        ValueAvailability.PRESENT,
        ValueAvailability.NOT_APPLICABLE,
        ValueAvailability.MISSING_OR_UNSPECIFIED,
        ValueAvailability.UNKNOWN,
    } == set(ValueAvailability)
