"""`lib.global_market.model.GlobalMarketRecord`/Enum群のTest(Phase4E-1)。"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from lib.evidence.model import AvailabilityBasis, Frequency, ValueAvailability
from lib.global_market.model import (
    AdjustmentStatus,
    GlobalMarketRecord,
    IndexReturnType,
    InstrumentCategory,
    PriceType,
)

RETRIEVED_AT = datetime(2026, 8, 19, 9, 0, tzinfo=UTC)


def _base_record(**overrides: object) -> GlobalMarketRecord:
    base: dict[str, object] = {
        "record_id": "GM_1",
        "series_id": "SPX_PRICE_INDEX:PROVIDER:DAILY:2026-08-18",
        "instrument_category": InstrumentCategory.EQUITY_INDEX,
        "index_return_type": IndexReturnType.PRICE_RETURN,
        "metric_name": "SPX_PRICE_INDEX",
        "source_id": "PROVIDER",
        "frequency": Frequency.DAILY,
        "session_date": date(2026, 8, 18),
        "market_timezone": "America/New_York",
        "raw_value": "5000.12",
        "value": Decimal("5000.12"),
        "unit": "index points",
        "currency": None,
        "value_availability": ValueAvailability.PRESENT,
        "retrieved_at": RETRIEVED_AT,
        "normalizer_version": "TEST_V1",
    }
    base.update(overrides)
    return GlobalMarketRecord(**base)


def test_retrieved_at_requires_tz_aware() -> None:
    with pytest.raises(ValueError, match="tz-aware"):
        _base_record(retrieved_at=datetime(2026, 8, 19, 9, 0))


def test_observation_time_requires_tz_aware_when_present() -> None:
    with pytest.raises(ValueError, match="tz-aware"):
        _base_record(observation_time=datetime(2026, 8, 18, 16, 0))


def test_market_public_at_requires_tz_aware_when_present() -> None:
    with pytest.raises(ValueError, match="tz-aware"):
        _base_record(market_public_at=datetime(2026, 8, 18, 16, 0))


def test_market_public_at_basis_forced_unknown_when_value_absent() -> None:
    with pytest.raises(ValueError, match="market_public_at"):
        _base_record(market_public_at=None, market_public_at_basis=AvailabilityBasis.EXACT)


def test_empty_market_timezone_rejected() -> None:
    with pytest.raises(ValueError, match="market_timezone"):
        _base_record(market_timezone="")


def test_explicit_observation_time_is_accepted() -> None:
    from zoneinfo import ZoneInfo

    close = datetime(2026, 8, 18, 16, 0, tzinfo=ZoneInfo("America/New_York"))
    record = _base_record(observation_time=close)
    assert record.observation_time == close


def test_series_code_and_exchange_default_to_none_not_guessed() -> None:
    record = _base_record()
    assert record.series_code is None
    assert record.exchange is None


def test_series_code_only_set_when_explicitly_supplied() -> None:
    record = _base_record(series_code="^GSPC", exchange="NYSE")
    assert record.series_code == "^GSPC"
    assert record.exchange == "NYSE"


def test_index_return_type_defaults_to_not_applicable_for_non_index() -> None:
    fx_record = _base_record(
        series_id="USDJPY:PROVIDER:DAILY:2026-08-18",
        instrument_category=InstrumentCategory.FX,
        index_return_type=IndexReturnType.NOT_APPLICABLE,
        metric_name="USDJPY",
        currency="JPY",
    )
    assert fx_record.index_return_type == IndexReturnType.NOT_APPLICABLE


def test_price_index_and_total_return_are_distinct_enum_values() -> None:
    price = _base_record(index_return_type=IndexReturnType.PRICE_RETURN)
    total = _base_record(index_return_type=IndexReturnType.TOTAL_RETURN)
    assert price.index_return_type != total.index_return_type


def test_price_type_defaults_to_not_applicable() -> None:
    record = _base_record()
    assert record.price_type == PriceType.NOT_APPLICABLE


def test_commodity_price_type_distinguishes_spot_from_continuous_futures() -> None:
    spot = _base_record(
        series_id="WTI_SPOT:PROVIDER:DAILY:2026-08-18",
        instrument_category=InstrumentCategory.COMMODITY,
        index_return_type=IndexReturnType.NOT_APPLICABLE,
        price_type=PriceType.SPOT,
        metric_name="WTI_SPOT",
        currency="USD",
    )
    continuous = _base_record(
        series_id="WTI_CONTINUOUS:PROVIDER:DAILY:2026-08-18",
        instrument_category=InstrumentCategory.COMMODITY,
        index_return_type=IndexReturnType.NOT_APPLICABLE,
        price_type=PriceType.CONTINUOUS_FUTURES,
        metric_name="WTI_CONTINUOUS",
        currency="USD",
    )
    assert spot.price_type != continuous.price_type


def test_adjustment_status_defaults_to_unknown_not_adjusted() -> None:
    record = _base_record()
    assert record.adjustment_status == AdjustmentStatus.UNKNOWN


def test_currency_and_unit_are_distinct_axes() -> None:
    record = _base_record(currency="USD", unit="index points")
    assert record.currency == "USD"
    assert record.unit == "index points"


def test_instrument_category_values_are_distinct() -> None:
    assert {c.value for c in InstrumentCategory} == {
        "EQUITY_INDEX",
        "FX",
        "RATE",
        "COMMODITY",
        "VOLATILITY_INDEX",
        "UNKNOWN",
    }
