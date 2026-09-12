"""`lib.positioning.normalize`/`lib.positioning.view`/`lib.positioning.evidence`の
PIT Test(Phase4C)。Test IDはユーザーTask仕様のPOS-*に対応する(期待値は
Phase4C要件から導出、実装からのコピーではない)。
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from lib.evidence.model import AvailabilityBasis, DataLayer, ValueAvailability
from lib.market_calendar import session_close_at, session_open_at
from lib.positioning.derived.price_derived import resolve_available_at
from lib.positioning.evidence import positioning_record_to_evidence
from lib.positioning.model import Frequency, PositioningRecord
from lib.positioning.normalize import build_revision_histories
from lib.positioning.view import positioning_as_of
from lib.sources.catalog import SourceAuthorityClass

RETRIEVED_AT = datetime(2026, 8, 18, 12, 0, tzinfo=UTC)


def _record(
    *,
    record_id: str,
    series_id: str = "7203:TURNOVER_VALUE:PRICE_DERIVED:DAILY",
    observation_start: date,
    observation_end: date,
    metric_type: str = "TURNOVER_VALUE",
    value: str = "1000",
    retrieved_at: datetime = RETRIEVED_AT,
) -> PositioningRecord:
    return PositioningRecord(
        record_id=record_id,
        series_id=series_id,
        entity_code="7203",
        metric_type=metric_type,
        source_id="PRICE_DERIVED",
        frequency=Frequency.DAILY,
        observation_start=observation_start,
        observation_end=observation_end,
        raw_value=value,
        value=Decimal(value),
        unit="JPY",
        value_availability=ValueAvailability.PRESENT,
        retrieved_at=retrieved_at,
        normalizer_version="TEST_V1",
    )


# --- POS-001: Observation Period Is Not Availability ---


def test_pos001_available_before_observation_end_session_close_is_not_usable() -> None:
    record = _record(record_id="R1", observation_start=date(2026, 8, 10), observation_end=date(2026, 8, 14))
    histories = build_revision_histories([record], resolve_available_at=resolve_available_at)
    decision_at = session_open_at(date(2026, 8, 14))  # 観測期間終了日の寄付(大引け前)
    result = positioning_as_of(histories, decision_at)
    assert result[record.series_id] is None


def test_pos001_available_at_observation_end_session_close_is_usable() -> None:
    record = _record(record_id="R1", observation_start=date(2026, 8, 10), observation_end=date(2026, 8, 14))
    histories = build_revision_histories([record], resolve_available_at=resolve_available_at)
    decision_at = session_close_at(date(2026, 8, 14))
    result = positioning_as_of(histories, decision_at)
    assert result[record.series_id] is not None
    assert result[record.series_id].value == "1000"


# --- POS-002: Publication Lag PIT(period_endとavailabilityの分離) ---


def test_pos002_as_of_between_period_end_and_availability_is_unavailable() -> None:
    """observation_endの日の寄付(period自体は終わっているがまだ大引け前)は
    利用不可(available_at=session_close_atより前)。"""
    record = _record(record_id="R1", observation_start=date(2026, 8, 18), observation_end=date(2026, 8, 18))
    histories = build_revision_histories([record], resolve_available_at=resolve_available_at)
    just_before_close = session_close_at(date(2026, 8, 18)).replace(hour=14)
    result = positioning_as_of(histories, just_before_close)
    assert result[record.series_id] is None


# --- POS-003: Unknown Provider Availability ---


def test_pos003_unknown_availability_basis_excluded_by_default() -> None:
    record = _record(record_id="R1", observation_start=date(2026, 8, 18), observation_end=date(2026, 8, 18))

    def _unknown_resolver(r: PositioningRecord) -> tuple[datetime, AvailabilityBasis]:
        return session_close_at(r.observation_end), AvailabilityBasis.UNKNOWN

    histories = build_revision_histories([record], resolve_available_at=_unknown_resolver)
    far_future = datetime(2030, 1, 1, tzinfo=UTC)
    result = positioning_as_of(histories, far_future)
    assert result[record.series_id] is None  # UNKNOWN basisは既定で除外(安全側)


def test_pos003_unknown_availability_included_only_when_explicit() -> None:
    record = _record(record_id="R1", observation_start=date(2026, 8, 18), observation_end=date(2026, 8, 18))

    def _unknown_resolver(r: PositioningRecord) -> tuple[datetime, AvailabilityBasis]:
        return session_close_at(r.observation_end), AvailabilityBasis.UNKNOWN

    histories = build_revision_histories([record], resolve_available_at=_unknown_resolver)
    far_future = datetime(2030, 1, 1, tzinfo=UTC)
    result = positioning_as_of(histories, far_future, include_unknown_availability=True)
    assert result[record.series_id] is not None


# --- POS-004: Current State Leakage ---


def test_pos004_historical_as_of_does_not_see_later_version() -> None:
    early = _record(record_id="R_EARLY", observation_start=date(2026, 8, 10), observation_end=date(2026, 8, 10), value="900")
    later = _record(record_id="R_LATER", observation_start=date(2026, 8, 17), observation_end=date(2026, 8, 17), value="1200")
    histories = build_revision_histories([early, later], resolve_available_at=resolve_available_at)
    decision_at = session_close_at(date(2026, 8, 10))
    result = positioning_as_of(histories, decision_at)
    assert result[early.series_id] is not None
    assert result[early.series_id].value == "900"


# --- POS-006: No Signal Inference(Evidence Content に解釈語を含まない) ---


def test_pos006_evidence_content_has_no_interpretive_language() -> None:
    record = _record(record_id="R1", observation_start=date(2026, 8, 18), observation_end=date(2026, 8, 18))
    evidence = positioning_record_to_evidence(
        record,
        layer=DataLayer.DERIVED,
        source_authority_class=SourceAuthorityClass.PRIMARY_OFFICIAL,
        originating_source="PRICE_DERIVED",
        delivery_provider="PRICE_DERIVED",
    )
    forbidden_terms = (
        "bullish",
        "bearish",
        "buy",
        "sell",
        "overhang",
        "squeeze",
        "crowding",
        "好調",
        "割安",
        "強気",
        "上昇要因",
        "好材料",
        "売り時",
        "買い時",
    )
    for term in forbidden_terms:
        assert term not in evidence.content, f"Evidence Contentに解釈語 '{term}' が含まれています"


# --- POS-007: Raw Change Is Not Revision(構造確認) ---


def test_pos007_positioning_modules_never_import_document_relationship() -> None:
    import lib.positioning.derived.price_derived as price_derived_module
    import lib.positioning.evidence as evidence_module
    import lib.positioning.model as model_module
    import lib.positioning.normalize as normalize_module

    for module in (model_module, normalize_module, evidence_module, price_derived_module):
        source = module.__file__
        assert source is not None
        text = open(source, encoding="utf-8").read()
        assert "DocumentRelationship" not in text
        assert "DuplicateRelationKind" not in text


# --- POS-009: Timezone Awareness ---


def test_pos009_naive_decision_at_rejected_by_positioning_as_of() -> None:
    with pytest.raises(ValueError, match="tz-aware"):
        positioning_as_of({}, datetime(2026, 8, 18, 12, 0))


def test_pos009_resolver_returning_naive_datetime_rejected() -> None:
    record = _record(record_id="R1", observation_start=date(2026, 8, 18), observation_end=date(2026, 8, 18))

    def _naive_resolver(r: PositioningRecord) -> tuple[datetime, AvailabilityBasis]:
        return datetime(2026, 8, 18, 15, 0), AvailabilityBasis.INFERRED

    with pytest.raises(ValueError, match="tz-aware"):
        build_revision_histories([record], resolve_available_at=_naive_resolver)


# --- POS-011: Future Injection ---


def test_pos011_future_observation_not_visible_to_past_as_of() -> None:
    future_record = _record(
        record_id="R_FUTURE", observation_start=date(2030, 1, 1), observation_end=date(2030, 1, 1), value="9999"
    )
    histories = build_revision_histories([future_record], resolve_available_at=resolve_available_at)
    past_decision_at = session_close_at(date(2026, 8, 18))
    result = positioning_as_of(histories, past_decision_at)
    assert result[future_record.series_id] is None


# --- POS-012: Source-specific semantics(共通Scoreへ潰さない) ---


def test_pos012_distinct_metric_types_produce_distinct_series() -> None:
    turnover = _record(
        record_id="R1",
        series_id="7203:TURNOVER_VALUE:PRICE_DERIVED:DAILY",
        metric_type="TURNOVER_VALUE",
        observation_start=date(2026, 8, 18),
        observation_end=date(2026, 8, 18),
    )
    volma = _record(
        record_id="R2",
        series_id="7203:VOLUME_MOVING_AVERAGE_20D:PRICE_DERIVED:DAILY",
        metric_type="VOLUME_MOVING_AVERAGE_20D",
        observation_start=date(2026, 8, 18),
        observation_end=date(2026, 8, 18),
    )
    histories = build_revision_histories([turnover, volma], resolve_available_at=resolve_available_at)
    assert turnover.series_id != volma.series_id
    assert set(histories.keys()) == {turnover.series_id, volma.series_id}


# --- Common Core Regression: 新規Evidence変換Primitiveを作らず既存を再利用 ---


def test_evidence_reuses_existing_evidence_record_and_source_metadata() -> None:
    record = _record(record_id="R1", observation_start=date(2026, 8, 18), observation_end=date(2026, 8, 18))
    evidence = positioning_record_to_evidence(
        record,
        layer=DataLayer.DERIVED,
        source_authority_class=SourceAuthorityClass.PRIMARY_OFFICIAL,
        originating_source="PRICE_DERIVED",
        delivery_provider="PRICE_DERIVED",
    )
    assert evidence.source.originating_source == "PRICE_DERIVED"
    assert evidence.source.delivery_provider == "PRICE_DERIVED"
    # market_public_atへはFallbackしない(retrieved_atが安全な下限として使われる)。
    assert evidence.source.available_at == record.retrieved_at
    assert evidence.layer == DataLayer.DERIVED
