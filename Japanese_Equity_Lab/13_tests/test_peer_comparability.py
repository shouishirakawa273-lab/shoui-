"""`lib.peer.comparability`(Stage 3.17、D0095): Entity単位/Metric単位の
Comparability Guardを検証する。

Candidate ≠ Accepted Peerの核心: 同一Sector Codeを持つCandidateでも、
Classification MembershipがPIT-safeと確認できなければAcceptedにならない
(要件v1 §9)。
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from lib.peer.comparability import evaluate_peer_entity_eligibility, evaluate_peer_metric_comparability
from lib.peer.model import (
    AcceptedPeer,
    ExcludedPeerCandidate,
    PeerCandidate,
    PeerExclusionReason,
    PeerMetricAvailability,
    PeerMetricObservation,
    PeerMetricType,
)
from lib.universe import UniverseResolution

_JST = ZoneInfo("Asia/Tokyo")
_AS_OF = datetime(2024, 11, 15, 15, 0, tzinfo=_JST)
_TARGET = "7203"


def _candidate(code: str, classification_code: str = "3700") -> PeerCandidate:
    return PeerCandidate(
        entity_code=code,
        provider_code=f"{code}0",
        company_name=f"Company {code}",
        classification_system="TSE_SECTOR_33",
        classification_code=classification_code,
    )


# --- Entity Eligibility -------------------------------------------------------


def test_self_peer_rejected() -> None:
    result = evaluate_peer_entity_eligibility(
        _candidate(_TARGET),
        target_entity_code=_TARGET,
        target_classification_code="3700",
        universe_resolution=UniverseResolution.RESOLVED,
        as_of=_AS_OF,
    )
    assert isinstance(result.excluded, ExcludedPeerCandidate)
    assert PeerExclusionReason.SELF_PEER in result.excluded.reasons


def test_sector_mismatch_excluded() -> None:
    result = evaluate_peer_entity_eligibility(
        _candidate("6758", classification_code="3650"),
        target_entity_code=_TARGET,
        target_classification_code="3700",
        universe_resolution=UniverseResolution.RESOLVED,
        as_of=_AS_OF,
    )
    assert result.excluded is not None
    assert PeerExclusionReason.SECTOR_MISMATCH in result.excluded.reasons


def test_pit_classification_unavailable_excludes_even_same_sector() -> None:
    """同一Sector CodeでもUniverse Resolutionが未確認ならAcceptedにしない
    (要件v1 §9、fail closed)。"""
    result = evaluate_peer_entity_eligibility(
        _candidate("7267", classification_code="3700"),
        target_entity_code=_TARGET,
        target_classification_code="3700",
        universe_resolution=UniverseResolution.PARTIAL,
        as_of=_AS_OF,
    )
    assert result.excluded is not None
    assert PeerExclusionReason.CLASSIFICATION_UNAVAILABLE_PIT_SAFE in result.excluded.reasons


def test_same_sector_and_resolved_universe_accepted() -> None:
    result = evaluate_peer_entity_eligibility(
        _candidate("7267", classification_code="3700"),
        target_entity_code=_TARGET,
        target_classification_code="3700",
        universe_resolution=UniverseResolution.RESOLVED,
        as_of=_AS_OF,
    )
    assert isinstance(result.accepted, AcceptedPeer)
    assert result.accepted.entity_code == "7267"


# --- Metric Comparability -----------------------------------------------------


def _obs(
    entity_code: str,
    *,
    availability: PeerMetricAvailability = PeerMetricAvailability.AVAILABLE,
    value: Decimal | None = Decimal("10"),
    fiscal_period_end: date | None = date(2024, 3, 31),
    accounting_standard: str | None = "IFRS",
) -> PeerMetricObservation:
    if availability != PeerMetricAvailability.AVAILABLE:
        return PeerMetricObservation(
            entity_code=entity_code, metric_type=PeerMetricType.LATEST_REPORTED_FY_PER, as_of=_AS_OF, availability=availability
        )
    return PeerMetricObservation(
        entity_code=entity_code,
        metric_type=PeerMetricType.LATEST_REPORTED_FY_PER,
        as_of=_AS_OF,
        availability=availability,
        value=value,
        value_available_at=_AS_OF,
        fiscal_period_end=fiscal_period_end,
        accounting_standard=accounting_standard,
        source_evidence_id=f"EVID_{entity_code}",
    )


def test_metric_missing_on_peer_side_excludes() -> None:
    reasons = evaluate_peer_metric_comparability(
        PeerMetricType.LATEST_REPORTED_FY_PER,
        target_observation=_obs(_TARGET),
        peer_observation=_obs("7267", availability=PeerMetricAvailability.MISSING, value=None),
    )
    assert reasons == (PeerExclusionReason.METRIC_UNAVAILABLE,)


def test_both_available_and_comparable_no_reasons() -> None:
    reasons = evaluate_peer_metric_comparability(
        PeerMetricType.LATEST_REPORTED_FY_PER,
        target_observation=_obs(_TARGET),
        peer_observation=_obs("7267"),
    )
    assert reasons == ()


def test_fiscal_period_month_mismatch_excludes() -> None:
    reasons = evaluate_peer_metric_comparability(
        PeerMetricType.LATEST_REPORTED_FY_PER,
        target_observation=_obs(_TARGET, fiscal_period_end=date(2024, 3, 31)),
        peer_observation=_obs("7267", fiscal_period_end=date(2024, 12, 31)),
    )
    assert PeerExclusionReason.FISCAL_PERIOD_INCOMPARABLE in reasons


def test_accounting_standard_mismatch_excludes() -> None:
    reasons = evaluate_peer_metric_comparability(
        PeerMetricType.LATEST_REPORTED_FY_PER,
        target_observation=_obs(_TARGET, accounting_standard="IFRS"),
        peer_observation=_obs("7267", accounting_standard="JGAAP"),
    )
    assert PeerExclusionReason.ACCOUNTING_STANDARD_MISMATCH in reasons


def test_unknown_accounting_standard_not_flagged_as_mismatch() -> None:
    """片側がUnknown(None)の場合はConfirmed Mismatchとして扱わない(推測しない)。"""
    reasons = evaluate_peer_metric_comparability(
        PeerMetricType.LATEST_REPORTED_FY_PER,
        target_observation=_obs(_TARGET, accounting_standard="IFRS"),
        peer_observation=_obs("7267", accounting_standard=None),
    )
    assert PeerExclusionReason.ACCOUNTING_STANDARD_MISMATCH not in reasons


def test_stale_financial_data_beyond_threshold_excludes() -> None:
    reasons = evaluate_peer_metric_comparability(
        PeerMetricType.LATEST_REPORTED_FY_PER,
        target_observation=_obs(_TARGET, fiscal_period_end=date(2024, 3, 31)),
        peer_observation=_obs("7267", fiscal_period_end=date(2022, 3, 31)),  # 2 FY cycles behind
    )
    assert PeerExclusionReason.STALE_FINANCIAL_DATA in reasons


def test_one_fiscal_cycle_lag_not_stale() -> None:
    reasons = evaluate_peer_metric_comparability(
        PeerMetricType.LATEST_REPORTED_FY_PER,
        target_observation=_obs(_TARGET, fiscal_period_end=date(2024, 3, 31)),
        peer_observation=_obs("7267", fiscal_period_end=date(2023, 3, 31)),  # 1 FY cycle behind
    )
    assert PeerExclusionReason.STALE_FINANCIAL_DATA not in reasons


def test_metric_type_mismatch_raises() -> None:
    with pytest.raises(ValueError, match="metric_type"):
        evaluate_peer_metric_comparability(
            PeerMetricType.CURRENT_FY_COMPANY_FORECAST_PER,
            target_observation=_obs(_TARGET),
            peer_observation=_obs("7267"),
        )
