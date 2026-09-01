"""`lib.positioning.model.PositioningRecord`/`Frequency`のTest(Phase4C)。"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from lib.evidence.model import AvailabilityBasis, ValueAvailability
from lib.positioning.model import Frequency, PositioningRecord

RETRIEVED_AT = datetime(2026, 8, 18, 12, 0, tzinfo=UTC)


def _base_record(**overrides: object) -> PositioningRecord:
    base: dict[str, object] = {
        "record_id": "POS_1",
        "series_id": "7203:TURNOVER_VALUE:PRICE_DERIVED:DAILY",
        "entity_code": "7203",
        "metric_type": "TURNOVER_VALUE",
        "source_id": "PRICE_DERIVED",
        "frequency": Frequency.DAILY,
        "observation_start": date(2026, 8, 18),
        "observation_end": date(2026, 8, 18),
        "raw_value": "1000000",
        "value": Decimal("1000000"),
        "unit": "JPY",
        "value_availability": ValueAvailability.PRESENT,
        "retrieved_at": RETRIEVED_AT,
        "normalizer_version": "TEST_V1",
    }
    base.update(overrides)
    return PositioningRecord(**base)


def test_retrieved_at_requires_tz_aware() -> None:
    with pytest.raises(ValueError, match="tz-aware"):
        _base_record(retrieved_at=datetime(2026, 8, 18, 12, 0))


def test_market_public_at_requires_tz_aware_when_present() -> None:
    with pytest.raises(ValueError, match="tz-aware"):
        _base_record(market_public_at=datetime(2026, 8, 18, 15, 0))


def test_market_public_at_basis_forced_unknown_when_value_absent() -> None:
    with pytest.raises(ValueError, match="market_public_at"):
        _base_record(market_public_at=None, market_public_at_basis=AvailabilityBasis.EXACT)


def test_explicit_market_public_at_is_accepted() -> None:
    confirmed = datetime(2026, 8, 18, 15, 0, tzinfo=UTC)
    record = _base_record(market_public_at=confirmed, market_public_at_basis=AvailabilityBasis.EXACT)
    assert record.market_public_at == confirmed
    assert record.market_public_at_basis == AvailabilityBasis.EXACT


def test_observation_start_after_end_fails_closed() -> None:
    with pytest.raises(ValueError, match="observation_start"):
        _base_record(observation_start=date(2026, 8, 19), observation_end=date(2026, 8, 18))


def test_observation_start_equal_to_end_is_allowed() -> None:
    record = _base_record(observation_start=date(2026, 8, 18), observation_end=date(2026, 8, 18))
    assert record.observation_start == record.observation_end


def test_frequency_values_are_distinct_and_explicit() -> None:
    """Frequencyはlib.evidence.modelへCommon Core昇格済み(Phase4D、
    QUARTERLY/ANNUALをlib.macroが必要としたため)。Positioning自身が実際に
    使うMembership(DAILY/WEEKLY/MONTHLY/EVENT_DRIVEN/UNKNOWN)が引き続き
    存在することのみを確認する(Enum全体の完全一致は`test_evidence_
    model.py`側で確認する)。"""
    values = {f.value for f in Frequency}
    assert {"DAILY", "WEEKLY", "MONTHLY", "EVENT_DRIVEN", "UNKNOWN"}.issubset(values)
