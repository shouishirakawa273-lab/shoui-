"""Phase3D(D0040): Decision Evidence Logのテスト。

ここではBUY/SELL Agentは実装しない。Schemaが正しく組み立てられることのみ確認する。
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from lib.evidence.decision_log import DecisionEvidenceLog


def test_decision_evidence_log_round_trip_fields() -> None:
    log = DecisionEvidenceLog(
        log_id="LOG_1",
        decision_at=datetime(2024, 6, 1, tzinfo=UTC),
        evidence_packet_id="P1",
        used_evidence_ids=("E1", "E2"),
        not_used_or_unavailable_evidence_ids=("E3",),
        main_drivers=("E1",),
        contradictions=("E2",),
        unknowns=("E4",),
    )
    assert log.used_evidence_ids == ("E1", "E2")
    assert log.predicted_outcome is None  # BUY/SELL Agent未実装のため既定でNone
    assert log.actual_outcome is None


def test_decision_evidence_log_requires_tz_aware_decision_at() -> None:
    with pytest.raises(ValueError, match="tz-aware"):
        DecisionEvidenceLog(log_id="LOG_1", decision_at=datetime(2024, 6, 1), evidence_packet_id="P1")


def test_decision_evidence_log_rejects_overlap_between_used_and_not_used() -> None:
    with pytest.raises(ValueError, match="重複"):
        DecisionEvidenceLog(
            log_id="LOG_1",
            decision_at=datetime(2024, 6, 1, tzinfo=UTC),
            evidence_packet_id="P1",
            used_evidence_ids=("E1",),
            not_used_or_unavailable_evidence_ids=("E1",),
        )
