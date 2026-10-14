"""`lib.macro_events.{model,surprise,store}`(D0110.1)のRegression
Test(D0110.1 §27-32 Required Tests)。

1. CPI/FOMC Acceptance Scenario(§27/§28)——複数のConsensus Snapshot
   が共存しいずれも上書きされないこと、FOMCの複数Dimensionが独立した
   Surpriseを生成し集約Scoreが存在しないこと。
2. Identity/Immutability(§29)——Event識別子の安定性、異なるSnapshot
   時刻の区別、重複ID Reject、改竄検知、順序非依存性。
3. PIT(§30)——Pre-Release Consensusのみ許可、Post-Release/Unavailable
   Consensusの拒否、未来のFirst Releaseの拒否、tz-naive入力の型的
   拒否。
4. Surprise(§31)——PP/BP計算の正しさ、Unit不一致・Identity不一致・
   Dimension不一致・Consensus/First Release欠落の拒否、複数Dimension
   の独立性、集約Surpriseの不在。
5. Historical Fidelity(§32)——First Release/Previous As
   Published/Consensus Snapshotが後続の入力で変化しないこと。
"""

from __future__ import annotations

import ast
import tempfile
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from lib.evaluation.integrity import verify_record_integrity
from lib.macro_events import model as macro_model_module
from lib.macro_events import store as macro_store_module
from lib.macro_events import surprise as macro_surprise_module
from lib.macro_events.model import (
    DIMENSION_CPI_HEADLINE_YOY,
    DIMENSION_FOMC_DOT_MEDIAN,
    DIMENSION_FOMC_POLICY_RATE_TARGET,
    EVENT_TYPE_CPI,
    EVENT_TYPE_FOMC,
    MacroEvent,
    MacroEventSchemaError,
    build_macro_consensus_snapshot,
    build_macro_event,
    build_macro_first_release,
)
from lib.macro_events.store import (
    new_macro_consensus_snapshot_store,
    new_macro_event_store,
    new_macro_first_release_store,
    new_macro_surprise_store,
)
from lib.macro_events.surprise import (
    CALC_RULE_ACTUAL_MINUS_EXPECTED_BP_V1,
    CALC_RULE_ACTUAL_MINUS_EXPECTED_PP_V1,
    MacroSurpriseStatus,
    compute_macro_surprise,
)

_T = datetime(2026, 9, 10, 8, 30, tzinfo=UTC)


def _cpi_event() -> MacroEvent:
    return build_macro_event(
        event_id="US_CPI_2026_09",
        event_type=EVENT_TYPE_CPI,
        jurisdiction="US",
        scheduled_at=_T,
        event_period="2026-09",
        source_id="BLS_CALENDAR",
        schedule_available_at=datetime(2026, 8, 1, tzinfo=UTC),
        created_at=_T,
    )


def _fomc_event() -> MacroEvent:
    return build_macro_event(
        event_id="FOMC_2026_09_16",
        event_type=EVENT_TYPE_FOMC,
        jurisdiction="US",
        scheduled_at=_T,
        event_period="2026-09",
        source_id="FED_CALENDAR",
        schedule_available_at=datetime(2026, 7, 1, tzinfo=UTC),
        created_at=_T,
    )


def _consensus(
    *,
    consensus_snapshot_id: str,
    event_id: str,
    dimension: str = DIMENSION_CPI_HEADLINE_YOY,
    value: Decimal,
    snapshot_at: datetime,
    available_at: datetime | None = None,
    unit: str = "PERCENT",
):
    return build_macro_consensus_snapshot(
        consensus_snapshot_id=consensus_snapshot_id,
        event_id=event_id,
        dimension=dimension,
        value=value,
        unit=unit,
        consensus_snapshot_at=snapshot_at,
        available_at=available_at if available_at is not None else snapshot_at,
        provider="BLOOMBERG",
        source_id="BLOOMBERG_CONSENSUS",
        created_at=_T,
    )


def _release(
    *,
    release_id: str,
    event_id: str,
    dimension: str = DIMENSION_CPI_HEADLINE_YOY,
    actual: Decimal,
    public_at: datetime = _T,
    available_at: datetime | None = None,
    previous_as_published: Decimal | None = None,
    unit: str = "PERCENT",
):
    return build_macro_first_release(
        release_id=release_id,
        event_id=event_id,
        dimension=dimension,
        actual_first_release=actual,
        previous_as_published=previous_as_published,
        unit=unit,
        actual_public_at=public_at,
        available_at=available_at if available_at is not None else public_at,
        source_id="BLS",
        created_at=_T,
    )


# ============================================================
# D0110.1 §27: CPI Acceptance Scenario
# ============================================================


def test_27_cpi_two_consensus_snapshots_coexist_with_distinct_surprises() -> None:
    event = _cpi_event()
    snap_a = _consensus(
        consensus_snapshot_id="SNAP_A", event_id=event.event_id, value=Decimal("3.0"), snapshot_at=_T - timedelta(days=3)
    )
    snap_b = _consensus(
        consensus_snapshot_id="SNAP_B", event_id=event.event_id, value=Decimal("3.1"), snapshot_at=_T - timedelta(minutes=5)
    )
    release = _release(release_id="REL1", event_id=event.event_id, actual=Decimal("3.3"), public_at=_T)

    result_a = compute_macro_surprise(
        surprise_id="SUR_A",
        event=event,
        consensus=snap_a,
        first_release=release,
        calculation_rule_id=CALC_RULE_ACTUAL_MINUS_EXPECTED_PP_V1,
        calculated_at=_T,
    )
    result_b = compute_macro_surprise(
        surprise_id="SUR_B",
        event=event,
        consensus=snap_b,
        first_release=release,
        calculation_rule_id=CALC_RULE_ACTUAL_MINUS_EXPECTED_PP_V1,
        calculated_at=_T,
    )
    assert result_a.status is MacroSurpriseStatus.SUCCESS
    assert result_b.status is MacroSurpriseStatus.SUCCESS
    assert result_a.surprise.surprise_value == Decimal("0.3")
    assert result_b.surprise.surprise_value == Decimal("0.2")
    # Neither consensus snapshot was mutated or overwritten.
    assert snap_a.value == Decimal("3.0")
    assert snap_b.value == Decimal("3.1")
    assert result_a.surprise.consensus_snapshot_id == "SNAP_A"
    assert result_b.surprise.consensus_snapshot_id == "SNAP_B"


# ============================================================
# D0110.1 §28: FOMC Acceptance Scenario
# ============================================================


def test_28_fomc_two_independent_surprise_dimensions_no_aggregate() -> None:
    event = _fomc_event()
    rate_consensus = _consensus(
        consensus_snapshot_id="RATE_SNAP",
        event_id=event.event_id,
        dimension=DIMENSION_FOMC_POLICY_RATE_TARGET,
        value=Decimal("4.50"),
        snapshot_at=_T - timedelta(days=1),
    )
    rate_release = _release(
        release_id="RATE_REL",
        event_id=event.event_id,
        dimension=DIMENSION_FOMC_POLICY_RATE_TARGET,
        actual=Decimal("4.25"),
        public_at=_T,
    )
    rate_result = compute_macro_surprise(
        surprise_id="RATE_SUR",
        event=event,
        consensus=rate_consensus,
        first_release=rate_release,
        calculation_rule_id=CALC_RULE_ACTUAL_MINUS_EXPECTED_BP_V1,
        calculated_at=_T,
    )

    dot_consensus = _consensus(
        consensus_snapshot_id="DOT_SNAP",
        event_id=event.event_id,
        dimension=DIMENSION_FOMC_DOT_MEDIAN,
        value=Decimal("3.50"),
        snapshot_at=_T - timedelta(days=1),
    )
    dot_release = _release(
        release_id="DOT_REL", event_id=event.event_id, dimension=DIMENSION_FOMC_DOT_MEDIAN, actual=Decimal("3.75"), public_at=_T
    )
    dot_result = compute_macro_surprise(
        surprise_id="DOT_SUR",
        event=event,
        consensus=dot_consensus,
        first_release=dot_release,
        calculation_rule_id=CALC_RULE_ACTUAL_MINUS_EXPECTED_BP_V1,
        calculated_at=_T,
    )

    assert rate_result.status is MacroSurpriseStatus.SUCCESS
    assert dot_result.status is MacroSurpriseStatus.SUCCESS
    assert rate_result.surprise.surprise_value == Decimal("-25.00")
    assert rate_result.surprise.surprise_unit == "BASIS_POINT"
    assert dot_result.surprise.surprise_value == Decimal("25.00")
    assert rate_result.surprise.surprise_id != dot_result.surprise.surprise_id
    assert rate_result.surprise.dimension != dot_result.surprise.dimension


# ============================================================
# D0110.1 §29: Identity / Immutability
# ============================================================


def test_29a_same_event_occurrence_has_stable_identity() -> None:
    event_1 = _cpi_event()
    event_2 = _cpi_event()
    assert event_1.event_id == event_2.event_id
    assert event_1.record_hash == event_2.record_hash


def test_29b_two_consensus_snapshot_times_remain_distinct() -> None:
    event = _cpi_event()
    snap_a = _consensus(
        consensus_snapshot_id="SNAP_A", event_id=event.event_id, value=Decimal("3.0"), snapshot_at=_T - timedelta(days=3)
    )
    snap_b = _consensus(
        consensus_snapshot_id="SNAP_B", event_id=event.event_id, value=Decimal("3.1"), snapshot_at=_T - timedelta(minutes=5)
    )
    assert snap_a.record_hash != snap_b.record_hash
    assert snap_a.consensus_snapshot_at != snap_b.consensus_snapshot_at


def test_29c_duplicate_id_different_content_fails_closed() -> None:
    from lib.errors import AppendOnlyViolationError

    event = _cpi_event()
    other_event = replace(event, event_period="2026-10")
    with tempfile.TemporaryDirectory() as d:
        store = new_macro_event_store(Path(d) / "events.jsonl")
        store.record(event)
        with pytest.raises(AppendOnlyViolationError):
            store.record(other_event)


def test_macro_event_store_allows_revised_event_version_to_coexist() -> None:
    """Regression(/code-review high指摘, D0110.1): `event_version`を
    上げた改訂Event(例: 延期)は、既存Versionと共存できる新しい
    Immutable Snapshotでなければならない(`lib.macro_events.model`の
    設計意図そのもの)。`event_id`単独Keyでは共存できずAppendOnly
    ViolationErrorになってしまっていた——`(event_id, event_version)`
    合成Keyで修正したことを確認する。"""
    from lib.errors import AppendOnlyViolationError

    original = _cpi_event()
    postponed = build_macro_event(
        event_id=original.event_id,
        event_type=original.event_type,
        jurisdiction=original.jurisdiction,
        scheduled_at=original.scheduled_at + timedelta(days=7),
        event_period=original.event_period,
        source_id=original.source_id,
        schedule_available_at=_T,
        created_at=_T,
        event_version=2,
    )
    with tempfile.TemporaryDirectory() as d:
        store = new_macro_event_store(Path(d) / "events.jsonl")
        store.record(original)
        store.record(postponed)  # must not raise

        all_records = store.all()
        assert len(all_records) == 2
        assert {r.event_version for r in all_records} == {1, 2}
        # 同一(event_id, event_version)の再記録は依然Rejectされる。
        with pytest.raises(AppendOnlyViolationError):
            store.record(original)


def test_29d_first_release_cannot_be_overwritten() -> None:
    from lib.errors import AppendOnlyViolationError

    event = _cpi_event()
    release = _release(release_id="REL1", event_id=event.event_id, actual=Decimal("3.3"))
    revised_release = replace(release, actual_first_release=Decimal("3.2"))
    with tempfile.TemporaryDirectory() as d:
        store = new_macro_first_release_store(Path(d) / "releases.jsonl")
        store.record(release)
        with pytest.raises(AppendOnlyViolationError):
            store.record(revised_release)
        assert store.get("REL1").actual_first_release == Decimal("3.3")


def test_29e_record_tampering_is_detected() -> None:
    event = _cpi_event()
    assert verify_record_integrity(event)
    tampered = replace(event, event_period="2099-01")
    assert not verify_record_integrity(tampered)

    release = _release(release_id="REL1", event_id=event.event_id, actual=Decimal("3.3"))
    assert verify_record_integrity(release)
    tampered_release = replace(release, actual_first_release=Decimal("999"))
    assert not verify_record_integrity(tampered_release)


def test_29e_frozen_dataclasses_reject_attribute_mutation() -> None:
    event = _cpi_event()
    with pytest.raises(FrozenInstanceError):
        event.event_period = "2099-01"  # type: ignore[misc]


def test_29f_repeated_construction_is_order_independent_and_deterministic() -> None:
    event = _cpi_event()
    snap_1 = _consensus(
        consensus_snapshot_id="SNAP_A", event_id=event.event_id, value=Decimal("3.0"), snapshot_at=_T - timedelta(days=3)
    )
    snap_2 = _consensus(
        consensus_snapshot_id="SNAP_A", event_id=event.event_id, value=Decimal("3.0"), snapshot_at=_T - timedelta(days=3)
    )
    assert snap_1.record_hash == snap_2.record_hash


# ============================================================
# D0110.1 §30: PIT
# ============================================================


def test_30a_pre_release_consensus_is_permitted() -> None:
    event = _cpi_event()
    consensus = _consensus(
        consensus_snapshot_id="SNAP1", event_id=event.event_id, value=Decimal("3.0"), snapshot_at=_T - timedelta(days=1)
    )
    release = _release(release_id="REL1", event_id=event.event_id, actual=Decimal("3.3"), public_at=_T)
    result = compute_macro_surprise(
        surprise_id="SUR1",
        event=event,
        consensus=consensus,
        first_release=release,
        calculation_rule_id=CALC_RULE_ACTUAL_MINUS_EXPECTED_PP_V1,
        calculated_at=_T,
    )
    assert result.status is MacroSurpriseStatus.SUCCESS


def test_30b_post_release_consensus_snapshot_is_rejected() -> None:
    event = _cpi_event()
    consensus = _consensus(
        consensus_snapshot_id="SNAP1", event_id=event.event_id, value=Decimal("3.0"), snapshot_at=_T + timedelta(hours=1)
    )
    release = _release(release_id="REL1", event_id=event.event_id, actual=Decimal("3.3"), public_at=_T)
    result = compute_macro_surprise(
        surprise_id="SUR1",
        event=event,
        consensus=consensus,
        first_release=release,
        calculation_rule_id=CALC_RULE_ACTUAL_MINUS_EXPECTED_PP_V1,
        calculated_at=_T,
    )
    assert result.status is MacroSurpriseStatus.PIT_INVALID


def test_30c_consensus_observed_pre_release_but_available_after_is_rejected() -> None:
    event = _cpi_event()
    consensus = _consensus(
        consensus_snapshot_id="SNAP1",
        event_id=event.event_id,
        value=Decimal("3.0"),
        snapshot_at=_T - timedelta(days=1),
        available_at=_T + timedelta(minutes=1),
    )
    release = _release(release_id="REL1", event_id=event.event_id, actual=Decimal("3.3"), public_at=_T)
    result = compute_macro_surprise(
        surprise_id="SUR1",
        event=event,
        consensus=consensus,
        first_release=release,
        calculation_rule_id=CALC_RULE_ACTUAL_MINUS_EXPECTED_PP_V1,
        calculated_at=_T,
    )
    assert result.status is MacroSurpriseStatus.PIT_INVALID


def test_30d_future_first_release_relative_to_decision_at_is_rejected() -> None:
    event = _cpi_event()
    consensus = _consensus(
        consensus_snapshot_id="SNAP1", event_id=event.event_id, value=Decimal("3.0"), snapshot_at=_T - timedelta(days=1)
    )
    release = _release(release_id="REL1", event_id=event.event_id, actual=Decimal("3.3"), public_at=_T, available_at=_T)
    result = compute_macro_surprise(
        surprise_id="SUR1",
        event=event,
        consensus=consensus,
        first_release=release,
        calculation_rule_id=CALC_RULE_ACTUAL_MINUS_EXPECTED_PP_V1,
        calculated_at=_T,
        decision_at=_T - timedelta(hours=1),
    )
    assert result.status is MacroSurpriseStatus.PIT_INVALID


def test_30e_naive_datetime_raises_typed_schema_error_not_type_error() -> None:
    with pytest.raises(MacroEventSchemaError):
        build_macro_event(
            event_id="US_CPI_2026_09",
            event_type=EVENT_TYPE_CPI,
            jurisdiction="US",
            scheduled_at=datetime(2026, 9, 10, 8, 30),  # noqa: DTZ001 -- 意図的にtz-naive
            event_period="2026-09",
            source_id="BLS_CALENDAR",
            schedule_available_at=datetime(2026, 8, 1, tzinfo=UTC),
            created_at=_T,
        )


def test_30f_no_implicit_timezone_conversion() -> None:
    import zoneinfo

    jst = zoneinfo.ZoneInfo("Asia/Tokyo")
    scheduled_at_jst = datetime(2026, 9, 10, 17, 30, tzinfo=jst)
    event = build_macro_event(
        event_id="US_CPI_2026_09",
        event_type=EVENT_TYPE_CPI,
        jurisdiction="US",
        scheduled_at=scheduled_at_jst,
        event_period="2026-09",
        source_id="BLS_CALENDAR",
        schedule_available_at=datetime(2026, 8, 1, tzinfo=UTC),
        created_at=_T,
    )
    # 元のTimezone表現(JST)がそのまま保持される——UTCへの暗黙変換は行わない。
    assert event.scheduled_at.tzinfo == jst
    assert event.scheduled_at == scheduled_at_jst


# ============================================================
# D0110.1 §31: Surprise
# ============================================================


def test_31a_cpi_pp_surprise_is_correct() -> None:
    event = _cpi_event()
    consensus = _consensus(
        consensus_snapshot_id="SNAP1", event_id=event.event_id, value=Decimal("3.0"), snapshot_at=_T - timedelta(days=1)
    )
    release = _release(release_id="REL1", event_id=event.event_id, actual=Decimal("3.3"))
    result = compute_macro_surprise(
        surprise_id="SUR1",
        event=event,
        consensus=consensus,
        first_release=release,
        calculation_rule_id=CALC_RULE_ACTUAL_MINUS_EXPECTED_PP_V1,
        calculated_at=_T,
    )
    assert result.surprise.surprise_value == Decimal("0.3")
    assert result.surprise.surprise_unit == "PERCENTAGE_POINT"


def test_31b_rate_bp_surprise_is_correct() -> None:
    event = _fomc_event()
    consensus = _consensus(
        consensus_snapshot_id="SNAP1",
        event_id=event.event_id,
        dimension=DIMENSION_FOMC_POLICY_RATE_TARGET,
        value=Decimal("4.50"),
        snapshot_at=_T - timedelta(days=1),
    )
    release = _release(
        release_id="REL1", event_id=event.event_id, dimension=DIMENSION_FOMC_POLICY_RATE_TARGET, actual=Decimal("4.25")
    )
    result = compute_macro_surprise(
        surprise_id="SUR1",
        event=event,
        consensus=consensus,
        first_release=release,
        calculation_rule_id=CALC_RULE_ACTUAL_MINUS_EXPECTED_BP_V1,
        calculated_at=_T,
    )
    assert result.surprise.surprise_value == Decimal("-25.00")
    assert result.surprise.surprise_unit == "BASIS_POINT"


def test_31c_incompatible_units_are_rejected() -> None:
    event = _cpi_event()
    consensus = _consensus(
        consensus_snapshot_id="SNAP1",
        event_id=event.event_id,
        value=Decimal("3.0"),
        snapshot_at=_T - timedelta(days=1),
        unit="PERCENTAGE_POINT",
    )
    release = _release(release_id="REL1", event_id=event.event_id, actual=Decimal("3.3"), unit="PERCENT")
    result = compute_macro_surprise(
        surprise_id="SUR1",
        event=event,
        consensus=consensus,
        first_release=release,
        calculation_rule_id=CALC_RULE_ACTUAL_MINUS_EXPECTED_PP_V1,
        calculated_at=_T,
    )
    assert result.status is MacroSurpriseStatus.UNIT_MISMATCH


def test_31d_mismatched_event_ids_are_rejected() -> None:
    event = _cpi_event()
    other_event = _fomc_event()
    consensus = _consensus(
        consensus_snapshot_id="SNAP1", event_id=other_event.event_id, value=Decimal("3.0"), snapshot_at=_T - timedelta(days=1)
    )
    release = _release(release_id="REL1", event_id=event.event_id, actual=Decimal("3.3"))
    result = compute_macro_surprise(
        surprise_id="SUR1",
        event=event,
        consensus=consensus,
        first_release=release,
        calculation_rule_id=CALC_RULE_ACTUAL_MINUS_EXPECTED_PP_V1,
        calculated_at=_T,
    )
    assert result.status is MacroSurpriseStatus.IDENTITY_MISMATCH


def test_31e_mismatched_dimensions_are_rejected() -> None:
    event = _fomc_event()
    consensus = _consensus(
        consensus_snapshot_id="SNAP1",
        event_id=event.event_id,
        dimension=DIMENSION_FOMC_POLICY_RATE_TARGET,
        value=Decimal("4.50"),
        snapshot_at=_T - timedelta(days=1),
    )
    release = _release(release_id="REL1", event_id=event.event_id, dimension=DIMENSION_FOMC_DOT_MEDIAN, actual=Decimal("3.75"))
    result = compute_macro_surprise(
        surprise_id="SUR1",
        event=event,
        consensus=consensus,
        first_release=release,
        calculation_rule_id=CALC_RULE_ACTUAL_MINUS_EXPECTED_BP_V1,
        calculated_at=_T,
    )
    assert result.status is MacroSurpriseStatus.INVALID_DIMENSION


def test_31f_missing_consensus_is_typed_result() -> None:
    event = _cpi_event()
    release = _release(release_id="REL1", event_id=event.event_id, actual=Decimal("3.3"))
    result = compute_macro_surprise(
        surprise_id="SUR1",
        event=event,
        consensus=None,
        first_release=release,
        calculation_rule_id=CALC_RULE_ACTUAL_MINUS_EXPECTED_PP_V1,
        calculated_at=_T,
    )
    assert result.status is MacroSurpriseStatus.MISSING_CONSENSUS


def test_31g_missing_first_release_is_typed_result() -> None:
    event = _cpi_event()
    consensus = _consensus(
        consensus_snapshot_id="SNAP1", event_id=event.event_id, value=Decimal("3.0"), snapshot_at=_T - timedelta(days=1)
    )
    result = compute_macro_surprise(
        surprise_id="SUR1",
        event=event,
        consensus=consensus,
        first_release=None,
        calculation_rule_id=CALC_RULE_ACTUAL_MINUS_EXPECTED_PP_V1,
        calculated_at=_T,
    )
    assert result.status is MacroSurpriseStatus.MISSING_FIRST_RELEASE


def test_31h_multiple_dimensions_remain_independent() -> None:
    event = _fomc_event()
    rate_consensus = _consensus(
        consensus_snapshot_id="RATE_SNAP",
        event_id=event.event_id,
        dimension=DIMENSION_FOMC_POLICY_RATE_TARGET,
        value=Decimal("4.50"),
        snapshot_at=_T - timedelta(days=1),
    )
    rate_release = _release(
        release_id="RATE_REL", event_id=event.event_id, dimension=DIMENSION_FOMC_POLICY_RATE_TARGET, actual=Decimal("4.25")
    )
    rate_result = compute_macro_surprise(
        surprise_id="RATE_SUR",
        event=event,
        consensus=rate_consensus,
        first_release=rate_release,
        calculation_rule_id=CALC_RULE_ACTUAL_MINUS_EXPECTED_BP_V1,
        calculated_at=_T,
    )

    dot_consensus = _consensus(
        consensus_snapshot_id="DOT_SNAP",
        event_id=event.event_id,
        dimension=DIMENSION_FOMC_DOT_MEDIAN,
        value=Decimal("3.50"),
        snapshot_at=_T - timedelta(days=1),
    )
    # Intentionally missing dot_release -- rate_result must remain SUCCESS
    # regardless of whether other dimensions have complete data.
    dot_result = compute_macro_surprise(
        surprise_id="DOT_SUR",
        event=event,
        consensus=dot_consensus,
        first_release=None,
        calculation_rule_id=CALC_RULE_ACTUAL_MINUS_EXPECTED_BP_V1,
        calculated_at=_T,
    )
    assert rate_result.status is MacroSurpriseStatus.SUCCESS
    assert dot_result.status is MacroSurpriseStatus.MISSING_FIRST_RELEASE


def test_31i_no_aggregate_surprise_field_or_result_exists() -> None:
    for module_path in (macro_model_module.__file__, macro_surprise_module.__file__, macro_store_module.__file__):
        identifiers = _module_identifiers(module_path)
        for forbidden in ("FOMC_SURPRISE", "aggregate_surprise", "surprise_score", "overall_surprise"):
            assert forbidden not in identifiers, f"{module_path} に禁止識別子 {forbidden!r} が含まれています"


# ============================================================
# D0110.1 §32: Historical Fidelity
# ============================================================


def test_32a_previous_as_published_survives_later_revision_input() -> None:
    release = _release(release_id="REL1", event_id="US_CPI_2026_09", actual=Decimal("3.3"), previous_as_published=Decimal("3.1"))
    # A later, revised historical value (3.0) must never retroactively
    # replace what was published at the time (3.1) -- constructing a
    # separately-built record with the revised value leaves the original
    # object's own field/hash completely untouched.
    assert release.previous_as_published == Decimal("3.1")
    later_revised_record = _release(
        release_id="REL1_REVISED", event_id="US_CPI_2026_09", actual=Decimal("3.3"), previous_as_published=Decimal("3.0")
    )
    assert release.previous_as_published == Decimal("3.1")
    assert later_revised_record.previous_as_published == Decimal("3.0")
    assert release.record_hash != later_revised_record.record_hash


def test_32b_first_release_survives_later_revised_actual() -> None:
    from lib.errors import AppendOnlyViolationError

    release = _release(release_id="REL1", event_id="US_CPI_2026_09", actual=Decimal("3.3"))
    revised = replace(release, actual_first_release=Decimal("3.2"))
    with tempfile.TemporaryDirectory() as d:
        store = new_macro_first_release_store(Path(d) / "releases.jsonl")
        store.record(release)
        with pytest.raises(AppendOnlyViolationError):
            store.record(revised)
        assert store.get("REL1").actual_first_release == Decimal("3.3")


def test_32c_earlier_consensus_survives_later_consensus_update() -> None:
    from lib.errors import AppendOnlyViolationError

    event = _cpi_event()
    snap_a = _consensus(
        consensus_snapshot_id="SNAP_A", event_id=event.event_id, value=Decimal("3.0"), snapshot_at=_T - timedelta(days=3)
    )
    conflicting_snap_a = replace(snap_a, value=Decimal("9.9"))
    with tempfile.TemporaryDirectory() as d:
        store = new_macro_consensus_snapshot_store(Path(d) / "consensus.jsonl")
        store.record(snap_a)
        with pytest.raises(AppendOnlyViolationError):
            store.record(conflicting_snap_a)
        assert store.get("SNAP_A").value == Decimal("3.0")


def test_32d_historical_surprise_continues_referencing_original_records() -> None:
    event = _cpi_event()
    consensus = _consensus(
        consensus_snapshot_id="SNAP_A", event_id=event.event_id, value=Decimal("3.0"), snapshot_at=_T - timedelta(days=3)
    )
    release = _release(release_id="REL1", event_id=event.event_id, actual=Decimal("3.3"))
    result = compute_macro_surprise(
        surprise_id="SUR1",
        event=event,
        consensus=consensus,
        first_release=release,
        calculation_rule_id=CALC_RULE_ACTUAL_MINUS_EXPECTED_PP_V1,
        calculated_at=_T,
    )
    assert result.surprise.consensus_snapshot_id == "SNAP_A"
    assert result.surprise.first_release_id == "REL1"
    # Even if a caller later builds a conflicting consensus/release object
    # in memory, the existing MacroSurprise keeps pointing at the IDs it
    # was actually computed from.
    _conflicting = replace(consensus, value=Decimal("9.9"))
    assert result.surprise.expected_value == Decimal("3.0")


# ============================================================
# Store round-trip
# ============================================================


def test_store_round_trip_all_four_record_types() -> None:
    event = _cpi_event()
    consensus = _consensus(
        consensus_snapshot_id="SNAP_A", event_id=event.event_id, value=Decimal("3.0"), snapshot_at=_T - timedelta(days=3)
    )
    release = _release(release_id="REL1", event_id=event.event_id, actual=Decimal("3.3"))
    surprise_result = compute_macro_surprise(
        surprise_id="SUR1",
        event=event,
        consensus=consensus,
        first_release=release,
        calculation_rule_id=CALC_RULE_ACTUAL_MINUS_EXPECTED_PP_V1,
        calculated_at=_T,
    )
    with tempfile.TemporaryDirectory() as d:
        base = Path(d)
        event_store = new_macro_event_store(base / "events.jsonl")
        consensus_store = new_macro_consensus_snapshot_store(base / "consensus.jsonl")
        release_store = new_macro_first_release_store(base / "releases.jsonl")
        surprise_store = new_macro_surprise_store(base / "surprises.jsonl")

        event_store.record(event)
        consensus_store.record(consensus)
        release_store.record(release)
        surprise_store.record(surprise_result.surprise)

        assert event_store.get(f"{event.event_id}::v{event.event_version}") == event
        assert consensus_store.get("SNAP_A") == consensus
        assert release_store.get("REL1") == release
        assert surprise_store.get("SUR1") == surprise_result.surprise


# ============================================================
# Scope Boundary: No Proprietary Forecast / Cross-Asset / Causal /
# Company Exposure / LLM / H0001
# ============================================================


def _module_identifiers(module_path: str) -> set[str]:
    source = Path(module_path).read_text(encoding="utf-8")
    tree = ast.parse(source)
    identifiers: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name | ast.Attribute):
            identifiers.add(getattr(node, "id", getattr(node, "attr", "")))
        elif isinstance(node, ast.arg):
            identifiers.add(node.arg)
        elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            identifiers.add(node.name)
    return identifiers


_MACRO_EVENTS_MODULES = (
    macro_model_module.__file__,
    macro_surprise_module.__file__,
    macro_store_module.__file__,
)


def test_no_proprietary_macro_forecast() -> None:
    for module_path in _MACRO_EVENTS_MODULES:
        identifiers = _module_identifiers(module_path)
        for forbidden in ("OurForecast", "our_cpi_forecast", "our_fomc_forecast", "our_rate_forecast", "ProprietaryForecast"):
            assert forbidden not in identifiers


def test_no_cross_asset_transmission() -> None:
    for module_path in _MACRO_EVENTS_MODULES:
        source = Path(module_path).read_text(encoding="utf-8")
        for forbidden in ("USDJPY", "treasury_response", "gold_response", "copper_response", "topix_response", "price_reaction"):
            assert forbidden not in source


def test_no_causal_inference() -> None:
    for module_path in _MACRO_EVENTS_MODULES:
        identifiers = _module_identifiers(module_path)
        for forbidden in ("causal_effect", "caused_by", "transmission_effect"):
            assert forbidden not in identifiers


def test_no_company_exposure() -> None:
    for module_path in _MACRO_EVENTS_MODULES:
        source = Path(module_path).read_text(encoding="utf-8")
        for forbidden in ("company_id", "profit_sensitivity", "operating_profit_impact", "stock_price_impact"):
            assert forbidden not in source


def test_no_decision_or_expected_return_logic() -> None:
    for module_path in _MACRO_EVENTS_MODULES:
        identifiers = _module_identifiers(module_path)
        for forbidden in ("BUY", "SELL", "expected_return", "DecisionRecord", "build_decision_record"):
            assert forbidden not in identifiers


def test_no_llm_dependency() -> None:
    for module_path in _MACRO_EVENTS_MODULES:
        source = Path(module_path).read_text(encoding="utf-8")
        for forbidden in ("import openai", "import anthropic", "requests.post", "httpx.", ".classify(", ".extract("):
            assert forbidden not in source


def test_modules_do_not_touch_h0001() -> None:
    for module_path in _MACRO_EVENTS_MODULES:
        source = Path(module_path).read_text(encoding="utf-8")
        assert "H0001" not in source
        assert "locked_test" not in source.lower()


def test_does_not_modify_or_duplicate_existing_macro_module() -> None:
    """既存`lib.macro.model.MacroRecord`(Series中心)を複製・変更
    していないこと、既存`lib.macro`パッケージを実際にImportしていない
    ことを確認する(D0110.1 §1/§2、衝突しない)。Docstring上の説明文で
    `lib.macro.model`へ言及すること自体は許容する(Import文のみを
    禁止対象とする)。"""
    for module_path in _MACRO_EVENTS_MODULES:
        source = Path(module_path).read_text(encoding="utf-8")
        assert "class MacroRecord" not in source
        for line in source.splitlines():
            stripped = line.strip()
            assert not stripped.startswith(("import lib.macro.", "from lib.macro.")), (
                f"{module_path} が既存lib.macroをImportしています: {stripped!r}"
            )


def test_does_not_modify_d0107_d0108_d0109_d0110() -> None:
    for module_path in _MACRO_EVENTS_MODULES:
        source = Path(module_path).read_text(encoding="utf-8")
        assert "class PredictionRecord" not in source
        assert "class ExpectationObservation" not in source
        assert "class FundamentalForecastResult" not in source
        assert "class ValuationResult" not in source
