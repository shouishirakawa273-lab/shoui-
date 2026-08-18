"""`lib.positioning.derived.price_derived`のTest(Phase4C)。Test IDはユーザーTask
仕様のPOS-*に対応する(期待値はPhase4C要件から導出、実装からのコピーではない)。
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from lib.evidence.model import AvailabilityBasis, ValueAvailability
from lib.positioning.derived.price_derived import (
    METRIC_TURNOVER_VALUE,
    build_turnover_value_records,
    build_volume_moving_average_records,
    resolve_available_at,
)
from lib.schemas.price_data import AdjustedOHLCVBar, RawOHLCVBar

RETRIEVED_AT = datetime(2026, 8, 18, 12, 0, tzinfo=UTC)


def _raw_bar(session_date: date, *, close: float | None, volume: float | None, code: str = "7203") -> RawOHLCVBar:
    return RawOHLCVBar(code=code, session_date=session_date, open=close, high=close, low=close, close=close, volume=volume)


def _adj_bar(session_date: date, *, volume: float | None, code: str = "7203") -> AdjustedOHLCVBar:
    return AdjustedOHLCVBar(
        code=code,
        session_date=session_date,
        open=1.0,
        high=1.0,
        low=1.0,
        close=1.0,
        volume=volume,
        split_adjustment_factor=1.0,
    )


# --- Basic correctness ---


def test_turnover_value_is_close_times_volume() -> None:
    bar = _raw_bar(date(2026, 8, 18), close=1000.0, volume=500.0)
    records = build_turnover_value_records([bar], retrieved_at=RETRIEVED_AT)
    assert len(records) == 1
    assert records[0].value == Decimal("500000.0")
    assert records[0].metric_type == METRIC_TURNOVER_VALUE
    assert records[0].value_availability == ValueAvailability.PRESENT


# --- POS-005: No Zero Fill ---


def test_pos005_missing_close_does_not_zero_fill() -> None:
    bar = _raw_bar(date(2026, 8, 18), close=None, volume=500.0)
    records = build_turnover_value_records([bar], retrieved_at=RETRIEVED_AT)
    assert records[0].value is None
    assert records[0].raw_value is None
    assert records[0].value_availability == ValueAvailability.MISSING_OR_UNSPECIFIED


def test_pos005_missing_volume_does_not_zero_fill() -> None:
    bar = _raw_bar(date(2026, 8, 18), close=1000.0, volume=None)
    records = build_turnover_value_records([bar], retrieved_at=RETRIEVED_AT)
    assert records[0].value is None
    assert records[0].value_availability == ValueAvailability.MISSING_OR_UNSPECIFIED


def test_pos005_insufficient_window_does_not_zero_fill() -> None:
    bars = [_adj_bar(date(2026, 8, d), volume=100.0) for d in range(11, 14)]  # 3 days, window=5
    records = build_volume_moving_average_records(bars, window=5, retrieved_at=RETRIEVED_AT)
    assert all(r.value is None for r in records)
    assert all(r.value_availability == ValueAvailability.MISSING_OR_UNSPECIFIED for r in records)


# --- POS-008: Frequency Preservation ---


def test_pos008_records_always_tagged_daily_frequency() -> None:
    bar = _raw_bar(date(2026, 8, 18), close=1000.0, volume=500.0)
    turnover = build_turnover_value_records([bar], retrieved_at=RETRIEVED_AT)
    volma = build_volume_moving_average_records([_adj_bar(date(2026, 8, 18), volume=100.0)], window=1, retrieved_at=RETRIEVED_AT)
    assert turnover[0].frequency.value == "DAILY"
    assert volma[0].frequency.value == "DAILY"


# --- POS-010: Entity Mapping Safety(推測しない: entity_codeは常にBar.codeそのまま) ---


def test_pos010_entity_code_taken_directly_from_bar_no_transformation() -> None:
    bar = _raw_bar(date(2026, 8, 18), close=1000.0, volume=500.0, code="6758")
    records = build_turnover_value_records([bar], retrieved_at=RETRIEVED_AT)
    assert records[0].entity_code == "6758"
    assert records[0].entity_code == bar.code


# --- Moving Average: window / minimum_periods ---


def test_volume_moving_average_uses_trailing_window() -> None:
    bars = [_adj_bar(date(2026, 8, d), volume=float(d)) for d in range(11, 16)]  # 11..15, 5 days
    records = build_volume_moving_average_records(bars, window=3, retrieved_at=RETRIEVED_AT)
    last = records[-1]  # 2026-08-15, trailing 3 = [13,14,15]
    assert last.observation_start == date(2026, 8, 13)
    assert last.observation_end == date(2026, 8, 15)
    assert last.value == Decimal(str((13.0 + 14.0 + 15.0) / 3))


def test_moving_average_minimum_periods_relaxation() -> None:
    bars = [_adj_bar(date(2026, 8, d), volume=100.0) for d in range(11, 13)]  # 2 days
    records = build_volume_moving_average_records(bars, window=5, minimum_periods=2, retrieved_at=RETRIEVED_AT)
    assert records[-1].value == Decimal("100.0")


def test_invalid_minimum_periods_rejected() -> None:
    bars = [_adj_bar(date(2026, 8, 11), volume=100.0)]
    with pytest.raises(ValueError, match="minimum_periods"):
        build_volume_moving_average_records(bars, window=3, minimum_periods=5, retrieved_at=RETRIEVED_AT)


def test_invalid_window_rejected() -> None:
    with pytest.raises(ValueError, match="window"):
        build_volume_moving_average_records([], window=0, retrieved_at=RETRIEVED_AT)


def test_naive_retrieved_at_rejected() -> None:
    with pytest.raises(ValueError, match="tz-aware"):
        build_turnover_value_records([], retrieved_at=datetime(2026, 8, 18, 12, 0))


# --- Determinism(Phase4C要件§33) ---


def test_determinism_same_input_same_output() -> None:
    bars = [_adj_bar(date(2026, 8, d), volume=float(d)) for d in range(11, 16)]
    first = build_volume_moving_average_records(bars, window=3, retrieved_at=RETRIEVED_AT)
    second = build_volume_moving_average_records(bars, window=3, retrieved_at=RETRIEVED_AT)
    assert [r.value for r in first] == [r.value for r in second]
    assert [r.record_id for r in first] == [r.record_id for r in second]


# --- resolve_available_at(INFERRED basis、session_close_at規約の再利用) ---


def test_resolve_available_at_uses_session_close_and_inferred_basis() -> None:
    record = build_turnover_value_records([_raw_bar(date(2026, 8, 18), close=1000.0, volume=500.0)], retrieved_at=RETRIEVED_AT)[0]
    available_at, basis = resolve_available_at(record)
    assert basis == AvailabilityBasis.INFERRED
    assert available_at.date() == date(2026, 8, 18)
    assert available_at.tzinfo is not None
