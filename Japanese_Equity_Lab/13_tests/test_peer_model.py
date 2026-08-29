"""`lib.peer.model`の型Invariant(Stage 3.17、D0095)。

Candidate vs Accepted Peerの区別・Self-Peer Exclusion・Same-As-Of Rule・
Sample Sufficiency Policy等、Peer Comparison Foundationの構造的契約を
Deterministic Fixtureで検証する(実7203 Runtimeに依存しない)。
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from lib.peer.model import (
    AcceptedPeer,
    ExcludedPeerCandidate,
    PeerAggregateContext,
    PeerCandidate,
    PeerComparisonRecord,
    PeerEntityComparabilityResult,
    PeerExclusionReason,
    PeerMetricAvailability,
    PeerMetricObservation,
    PeerMetricType,
    PeerUniverseSnapshot,
)
from lib.universe import UniverseResolution

_JST = ZoneInfo("Asia/Tokyo")
_AS_OF = datetime(2024, 11, 15, 15, 0, tzinfo=_JST)
_TARGET = "1000"


def _candidate(code: str, *, classification_code: str = "3700") -> PeerCandidate:
    return PeerCandidate(
        entity_code=code,
        provider_code=f"{code}0",
        company_name=f"Company {code}",
        classification_system="TSE_SECTOR_33",
        classification_code=classification_code,
    )


# --- PeerUniverseSnapshot ---------------------------------------------------


def test_universe_snapshot_rejects_self_peer_in_candidates() -> None:
    with pytest.raises(ValueError, match="Self-Peer"):
        PeerUniverseSnapshot(
            target_entity_code=_TARGET,
            as_of=_AS_OF,
            classification_system="TSE_SECTOR_33",
            target_classification_code="3700",
            candidates=(_candidate(_TARGET),),
        )


def test_universe_snapshot_rejects_duplicate_candidates() -> None:
    with pytest.raises(ValueError, match="重複"):
        PeerUniverseSnapshot(
            target_entity_code=_TARGET,
            as_of=_AS_OF,
            classification_system="TSE_SECTOR_33",
            target_classification_code="3700",
            candidates=(_candidate("2001"), _candidate("2001")),
        )


def test_universe_snapshot_rejects_unsorted_candidates() -> None:
    with pytest.raises(ValueError, match="昇順"):
        PeerUniverseSnapshot(
            target_entity_code=_TARGET,
            as_of=_AS_OF,
            classification_system="TSE_SECTOR_33",
            target_classification_code="3700",
            candidates=(_candidate("2002"), _candidate("2001")),
        )


def test_universe_snapshot_accepts_sorted_candidates() -> None:
    snapshot = PeerUniverseSnapshot(
        target_entity_code=_TARGET,
        as_of=_AS_OF,
        classification_system="TSE_SECTOR_33",
        target_classification_code="3700",
        candidates=(_candidate("2001"), _candidate("2002")),
        resolution=UniverseResolution.RESOLVED,
    )
    assert [c.entity_code for c in snapshot.candidates] == ["2001", "2002"]


def test_universe_snapshot_requires_tz_aware_as_of() -> None:
    with pytest.raises(ValueError, match="tz-aware"):
        PeerUniverseSnapshot(
            target_entity_code=_TARGET,
            as_of=datetime(2024, 11, 15, 15, 0),  # naive
            classification_system="TSE_SECTOR_33",
            target_classification_code="3700",
        )


# --- ExcludedPeerCandidate / PeerEntityComparabilityResult ------------------


def test_excluded_peer_candidate_requires_at_least_one_reason() -> None:
    with pytest.raises(ValueError, match="reasons"):
        ExcludedPeerCandidate(entity_code="2001", reasons=())


def test_entity_comparability_result_exactly_one_contract() -> None:
    accepted = AcceptedPeer(entity_code="2001", classification_system="TSE_SECTOR_33", classification_code="3700", as_of=_AS_OF)
    excluded = ExcludedPeerCandidate(entity_code="2001", reasons=(PeerExclusionReason.SELF_PEER,))
    with pytest.raises(ValueError, match="Exactly-One"):
        PeerEntityComparabilityResult(accepted=accepted, excluded=excluded)
    with pytest.raises(ValueError, match="Exactly-One"):
        PeerEntityComparabilityResult()
    # Exactly one is fine (no exception).
    PeerEntityComparabilityResult(accepted=accepted)
    PeerEntityComparabilityResult(excluded=excluded)


# --- PeerMetricObservation ---------------------------------------------------


def test_observation_available_requires_value_and_available_at_and_evidence_id() -> None:
    with pytest.raises(ValueError, match="valueがNone"):
        PeerMetricObservation(
            entity_code="2001",
            metric_type=PeerMetricType.LATEST_REPORTED_FY_PER,
            as_of=_AS_OF,
            availability=PeerMetricAvailability.AVAILABLE,
        )


def test_observation_available_rejects_future_available_at() -> None:
    with pytest.raises(ValueError, match="Same-As-Of Rule"):
        PeerMetricObservation(
            entity_code="2001",
            metric_type=PeerMetricType.LATEST_REPORTED_FY_PER,
            as_of=_AS_OF,
            availability=PeerMetricAvailability.AVAILABLE,
            value=Decimal("10"),
            value_available_at=_AS_OF.replace(year=_AS_OF.year + 1),
            source_evidence_id="EVID_X",
        )


def test_observation_missing_rejects_value_present() -> None:
    with pytest.raises(ValueError, match="Noneではありません"):
        PeerMetricObservation(
            entity_code="2001",
            metric_type=PeerMetricType.LATEST_REPORTED_FY_PER,
            as_of=_AS_OF,
            availability=PeerMetricAvailability.MISSING,
            value=Decimal("10"),
        )


def _available_observation(entity_code: str, value: Decimal, *, evidence_id: str | None = None) -> PeerMetricObservation:
    return PeerMetricObservation(
        entity_code=entity_code,
        metric_type=PeerMetricType.LATEST_REPORTED_FY_PER,
        as_of=_AS_OF,
        availability=PeerMetricAvailability.AVAILABLE,
        value=value,
        value_available_at=_AS_OF,
        source_evidence_id=evidence_id or f"EVID_{entity_code}",
    )


# --- PeerComparisonRecord ----------------------------------------------------


def test_comparison_record_rejects_self_peer() -> None:
    obs = _available_observation(_TARGET, Decimal("10"))
    with pytest.raises(ValueError, match="Self-Peer"):
        PeerComparisonRecord(
            target_entity_code=_TARGET,
            peer_entity_code=_TARGET,
            metric_type=PeerMetricType.LATEST_REPORTED_FY_PER,
            comparison_as_of=_AS_OF,
            target_observation=obs,
            peer_observation=obs,
        )


def test_comparison_record_comparable_requires_difference() -> None:
    target_obs = _available_observation(_TARGET, Decimal("10"))
    peer_obs = _available_observation("2001", Decimal("8"))
    with pytest.raises(ValueError, match="differenceが計算されていません"):
        PeerComparisonRecord(
            target_entity_code=_TARGET,
            peer_entity_code="2001",
            metric_type=PeerMetricType.LATEST_REPORTED_FY_PER,
            comparison_as_of=_AS_OF,
            target_observation=target_obs,
            peer_observation=peer_obs,
        )


def test_comparison_record_incomparable_rejects_difference() -> None:
    target_obs = _available_observation(_TARGET, Decimal("10"))
    peer_obs = _available_observation("2001", Decimal("8"))
    with pytest.raises(ValueError, match="Incomparable"):
        PeerComparisonRecord(
            target_entity_code=_TARGET,
            peer_entity_code="2001",
            metric_type=PeerMetricType.LATEST_REPORTED_FY_PER,
            comparison_as_of=_AS_OF,
            target_observation=target_obs,
            peer_observation=peer_obs,
            exclusion_reasons=(PeerExclusionReason.SECTOR_MISMATCH,),
            difference=Decimal("2"),
        )


def test_comparison_record_computes_exact_difference() -> None:
    target_obs = _available_observation(_TARGET, Decimal("10"))
    peer_obs = _available_observation("2001", Decimal("8"))
    record = PeerComparisonRecord(
        target_entity_code=_TARGET,
        peer_entity_code="2001",
        metric_type=PeerMetricType.LATEST_REPORTED_FY_PER,
        comparison_as_of=_AS_OF,
        target_observation=target_obs,
        peer_observation=peer_obs,
        difference=Decimal("2"),
    )
    assert record.difference == Decimal("2")


# --- PeerAggregateContext ----------------------------------------------------


def _context(peer_count: int = 3, minimum: int = 3) -> PeerAggregateContext:
    codes = tuple(f"200{i}" for i in range(1, peer_count + 1))
    evidence_ids = tuple(f"EVID_{c}" for c in codes)
    return PeerAggregateContext(
        target_entity_code=_TARGET,
        metric_type=PeerMetricType.LATEST_REPORTED_FY_PER,
        as_of=_AS_OF,
        target_value=Decimal("10"),
        target_observation_evidence_id=f"EVID_{_TARGET}",
        peer_count=peer_count,
        minimum_sample_count=minimum,
        included_peer_entity_codes=codes,
        included_peer_observation_evidence_ids=evidence_ids,
        peer_min=Decimal("7"),
        peer_median=Decimal("8"),
        peer_max=Decimal("9"),
        median_method="ORDERED_MIDPOINT",
        target_percentile=Decimal("100"),
        percentile_method="EMPIRICAL_CDF_LE",
        percentile_scale="PERCENT_0_100",
        available_at=_AS_OF,
    )


def test_aggregate_context_below_minimum_rejected() -> None:
    with pytest.raises(ValueError, match="Sample Sufficiency"):
        _context(peer_count=2, minimum=3)


def test_aggregate_context_at_minimum_accepted() -> None:
    ctx = _context(peer_count=3, minimum=3)
    assert ctx.peer_count == 3


def test_aggregate_context_rejects_self_in_included_peers() -> None:
    with pytest.raises(ValueError, match="Self-Peer"):
        PeerAggregateContext(
            target_entity_code=_TARGET,
            metric_type=PeerMetricType.LATEST_REPORTED_FY_PER,
            as_of=_AS_OF,
            target_value=Decimal("10"),
            target_observation_evidence_id=f"EVID_{_TARGET}",
            peer_count=3,
            minimum_sample_count=3,
            included_peer_entity_codes=(_TARGET, "2001", "2002"),
            included_peer_observation_evidence_ids=("EVID_A", "EVID_B", "EVID_C"),
            peer_min=Decimal("7"),
            peer_median=Decimal("8"),
            peer_max=Decimal("9"),
            median_method="ORDERED_MIDPOINT",
            target_percentile=Decimal("100"),
            percentile_method="EMPIRICAL_CDF_LE",
            percentile_scale="PERCENT_0_100",
            available_at=_AS_OF,
        )


def test_aggregate_context_rejects_min_median_max_out_of_order() -> None:
    ctx_kwargs = _context(peer_count=3, minimum=3).__dict__.copy()
    ctx_kwargs["peer_min"] = Decimal("9")  # min > max, structurally invalid
    with pytest.raises(ValueError, match="peer_min"):
        PeerAggregateContext(**ctx_kwargs)


def test_aggregate_context_rejects_percentile_out_of_range() -> None:
    ctx_kwargs = _context(peer_count=3, minimum=3).__dict__.copy()
    ctx_kwargs["target_percentile"] = Decimal("101")
    with pytest.raises(ValueError, match="target_percentile"):
        PeerAggregateContext(**ctx_kwargs)


def test_aggregate_context_rejects_evidence_id_count_mismatch() -> None:
    ctx_kwargs = _context(peer_count=3, minimum=3).__dict__.copy()
    ctx_kwargs["included_peer_observation_evidence_ids"] = ("EVID_ONLY_ONE",)
    with pytest.raises(ValueError, match="Dangling Parent Guard"):
        PeerAggregateContext(**ctx_kwargs)
