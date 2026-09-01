"""`lib.macro.model.MacroRecord`/`SeasonalAdjustment`のTest(Phase4D)。"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from lib.evidence.model import AvailabilityBasis, Frequency, ValueAvailability
from lib.macro.model import MacroRecord, SeasonalAdjustment

RETRIEVED_AT = datetime(2026, 8, 18, 12, 0, tzinfo=UTC)


def _base_record(**overrides: object) -> MacroRecord:
    base: dict[str, object] = {
        "record_id": "MACRO_1",
        "series_id": "JP_CPI_HEADLINE:ESTAT:MONTHLY",
        "metric_name": "CPI_HEADLINE",
        "source_id": "estat",
        "frequency": Frequency.MONTHLY,
        "reference_period_start": date(2026, 7, 1),
        "reference_period_end": date(2026, 7, 31),
        "raw_value": "103.2",
        "value": Decimal("103.2"),
        "unit": "index",
        "seasonal_adjustment": SeasonalAdjustment.NOT_SEASONALLY_ADJUSTED,
        "value_availability": ValueAvailability.PRESENT,
        "retrieved_at": RETRIEVED_AT,
        "normalizer_version": "TEST_V1",
    }
    base.update(overrides)
    return MacroRecord(**base)


def test_retrieved_at_requires_tz_aware() -> None:
    with pytest.raises(ValueError, match="tz-aware"):
        _base_record(retrieved_at=datetime(2026, 8, 18, 12, 0))


def test_market_public_at_requires_tz_aware_when_present() -> None:
    with pytest.raises(ValueError, match="tz-aware"):
        _base_record(market_public_at=datetime(2026, 8, 19, 8, 30))


def test_market_public_at_basis_forced_unknown_when_value_absent() -> None:
    with pytest.raises(ValueError, match="market_public_at"):
        _base_record(market_public_at=None, market_public_at_basis=AvailabilityBasis.EXACT)


def test_explicit_market_public_at_is_accepted() -> None:
    confirmed = datetime(2026, 8, 19, 8, 30, tzinfo=UTC)
    record = _base_record(market_public_at=confirmed, market_public_at_basis=AvailabilityBasis.EXACT)
    assert record.market_public_at == confirmed
    assert record.market_public_at_basis == AvailabilityBasis.EXACT


def test_reference_period_start_after_end_fails_closed() -> None:
    with pytest.raises(ValueError, match="reference_period_start"):
        _base_record(reference_period_start=date(2026, 8, 1), reference_period_end=date(2026, 7, 31))


def test_reference_period_start_equal_to_end_is_allowed() -> None:
    record = _base_record(reference_period_start=date(2026, 7, 31), reference_period_end=date(2026, 7, 31))
    assert record.reference_period_start == record.reference_period_end


def test_series_code_defaults_to_none_not_guessed() -> None:
    record = _base_record()
    assert record.series_code is None


def test_series_code_only_set_when_explicitly_supplied() -> None:
    record = _base_record(series_code="0001100001")
    assert record.series_code == "0001100001"


def test_vintage_label_defaults_to_none_not_inferred() -> None:
    record = _base_record()
    assert record.vintage_label is None


def test_vintage_label_only_set_when_explicitly_supplied() -> None:
    record = _base_record(vintage_label="PRELIMINARY")
    assert record.vintage_label == "PRELIMINARY"


def test_seasonal_adjustment_values_are_distinct() -> None:
    assert {s.value for s in SeasonalAdjustment} == {"SEASONALLY_ADJUSTED", "NOT_SEASONALLY_ADJUSTED", "UNKNOWN"}


def test_frequency_supports_quarterly_and_annual_for_macro_use() -> None:
    gdp = _base_record(frequency=Frequency.QUARTERLY)
    annual = _base_record(frequency=Frequency.ANNUAL)
    assert gdp.frequency == Frequency.QUARTERLY
    assert annual.frequency == Frequency.ANNUAL
