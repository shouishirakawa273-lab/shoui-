"""EvidenceRelationAssignment(Stage 3.15.2、D0091): NEUTRAL/UNKNOWN/
Omittedを既存Bucket表現より1段細かくLosslessに区別できることを検証する。

既存`unknowns`Bucketは`EvidenceRelation.NEUTRAL`・`EvidenceRelation.
UNKNOWN`・「そもそも`relations`に指定が無かった」の3状態を全て収束させる。
`relation_assignments`はそれらをFresh Process後も区別可能にする。
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from lib.evidence.model import DataLayer, EvidenceRecord, EvidenceRelation, EvidenceType
from lib.evidence.packet import EvidencePacket, EvidenceRelationAssignment, build_evidence_packet
from lib.sources.catalog import DataCapability, PrimaryOrSecondary, SourceAuthorityClass, SourceMetadata

_AS_OF = datetime(2024, 6, 1, tzinfo=UTC)


def _source() -> SourceMetadata:
    return SourceMetadata(
        source_id="s1",
        source_type="TDNET",
        provider_name="TDnet",
        source_authority_class=SourceAuthorityClass.PRIMARY_OFFICIAL,
        primary_or_secondary=PrimaryOrSecondary.PRIMARY,
        retrieved_at=datetime(2024, 1, 1, tzinfo=UTC),
        published_at=datetime(2024, 1, 1, tzinfo=UTC),
        available_at=datetime(2024, 1, 1, tzinfo=UTC),
    )


def _evidence(evidence_id: str) -> EvidenceRecord:
    return EvidenceRecord(
        evidence_id=evidence_id,
        evidence_type=EvidenceType.FACT,
        layer=DataLayer.NORMALIZED,
        capability=DataCapability.DISCLOSURE,
        content="内容",
        source=_source(),
    )


# --- §12: NEUTRAL/UNKNOWN/Omittedの3状態が区別可能 -----------------------------------------


def test_neutral_unknown_and_omitted_are_distinguishable_in_relation_assignments() -> None:
    a, b, c = _evidence("A"), _evidence("B"), _evidence("C")
    packet = build_evidence_packet(
        packet_id="P1",
        research_question="q",
        as_of=_AS_OF,
        evidence_pool=[a, b, c],
        relations={"A": EvidenceRelation.NEUTRAL, "B": EvidenceRelation.UNKNOWN},  # Cは意図的に省略
    )
    # Bucket上は3件とも unknowns へ収束する(既存挙動、変更なし)
    assert set(packet.unknowns) == {"A", "B", "C"}

    by_id = {assignment.evidence_id: assignment.relation for assignment in packet.relation_assignments}
    assert by_id["A"] == EvidenceRelation.NEUTRAL
    assert by_id["B"] == EvidenceRelation.UNKNOWN
    assert "C" not in by_id  # Omitted: Assignment自体が存在しない


def test_supports_contradicts_alternative_explanation_round_trip_in_assignments() -> None:
    e1, e2, e3 = _evidence("E1"), _evidence("E2"), _evidence("E3")
    packet = build_evidence_packet(
        packet_id="P1",
        research_question="q",
        as_of=_AS_OF,
        evidence_pool=[e1, e2, e3],
        relations={
            "E1": EvidenceRelation.SUPPORTS,
            "E2": EvidenceRelation.CONTRADICTS,
            "E3": EvidenceRelation.ALTERNATIVE_EXPLANATION,
        },
    )
    by_id = {assignment.evidence_id: assignment.relation for assignment in packet.relation_assignments}
    assert by_id["E1"] == EvidenceRelation.SUPPORTS
    assert by_id["E2"] == EvidenceRelation.CONTRADICTS
    assert by_id["E3"] == EvidenceRelation.ALTERNATIVE_EXPLANATION


def test_conflicting_evidence_ids_preserve_original_relation_assignment() -> None:
    """Critical Fix(D0091): Conflict Overrideは最終的なBucketだけを
    `contradictory_evidence`へ強制するが、Callerが`relations`へ明示指定した
    Exact Relationは消去しない(Losslessness)。"""
    fact_a, fact_b = _evidence("FACT_A"), _evidence("FACT_B")
    packet = build_evidence_packet(
        packet_id="P1",
        research_question="q",
        as_of=_AS_OF,
        evidence_pool=[fact_a, fact_b],
        relations={"FACT_A": EvidenceRelation.SUPPORTS, "FACT_B": EvidenceRelation.CONTRADICTS},
        conflicting_evidence_ids=["FACT_A", "FACT_B"],
    )
    assert set(packet.contradictory_evidence) == {"FACT_A", "FACT_B"}
    assert packet.positive_evidence == ()
    assert packet.negative_evidence == ()
    by_id = {a.evidence_id: a.relation for a in packet.relation_assignments}
    assert by_id["FACT_A"] == EvidenceRelation.SUPPORTS  # 元のExact Relationが保持される
    assert by_id["FACT_B"] == EvidenceRelation.CONTRADICTS


def test_conflicting_evidence_id_with_neutral_relation_preserves_neutral() -> None:
    e1 = _evidence("E1")
    packet = build_evidence_packet(
        packet_id="P1",
        research_question="q",
        as_of=_AS_OF,
        evidence_pool=[e1],
        relations={"E1": EvidenceRelation.NEUTRAL},
        conflicting_evidence_ids=["E1"],
    )
    assert "E1" in packet.contradictory_evidence
    assert "E1" not in packet.unknowns
    by_id = {a.evidence_id: a.relation for a in packet.relation_assignments}
    assert by_id["E1"] == EvidenceRelation.NEUTRAL


def test_conflicting_evidence_id_without_relation_has_no_assignment() -> None:
    """relationsに指定が無く、conflicting_evidence_idsにのみ存在するEvidenceは、
    Assignment自体を持たない(Relationとして指定された事実が無いため、要件v1 §4)。"""
    e1 = _evidence("E1")
    packet = build_evidence_packet(
        packet_id="P1",
        research_question="q",
        as_of=_AS_OF,
        evidence_pool=[e1],
        relations={},
        conflicting_evidence_ids=["E1"],
    )
    assert "E1" in packet.contradictory_evidence
    assigned_ids = {a.evidence_id for a in packet.relation_assignments}
    assert "E1" not in assigned_ids


# --- §7: Consistency Guard ------------------------------------------------------------------


def test_inconsistent_assignment_and_bucket_is_rejected() -> None:
    with pytest.raises(ValueError, match="不整合"):
        EvidencePacket(
            packet_id="P1",
            research_question="q",
            as_of=_AS_OF,
            included_evidence_ids=("E1",),
            negative_evidence=("E1",),
            relation_assignments=(EvidenceRelationAssignment(evidence_id="E1", relation=EvidenceRelation.SUPPORTS),),
            relation_assignments_tracked=True,
        )


def test_omitted_evidence_present_in_non_unknowns_bucket_is_rejected() -> None:
    with pytest.raises(ValueError, match="紛れ込んで"):
        EvidencePacket(
            packet_id="P1",
            research_question="q",
            as_of=_AS_OF,
            included_evidence_ids=("E1", "E2"),
            positive_evidence=("E1", "E2"),
            relation_assignments=(EvidenceRelationAssignment(evidence_id="E1", relation=EvidenceRelation.SUPPORTS),),
            relation_assignments_tracked=True,
        )


def test_duplicate_evidence_id_in_relation_assignments_is_rejected() -> None:
    with pytest.raises(ValueError, match="重複"):
        EvidencePacket(
            packet_id="P1",
            research_question="q",
            as_of=_AS_OF,
            included_evidence_ids=("E1",),
            positive_evidence=("E1",),
            relation_assignments=(
                EvidenceRelationAssignment(evidence_id="E1", relation=EvidenceRelation.SUPPORTS),
                EvidenceRelationAssignment(evidence_id="E1", relation=EvidenceRelation.SUPPORTS),
            ),
            relation_assignments_tracked=True,
        )


def test_relation_assignment_for_evidence_id_not_in_included_is_rejected() -> None:
    with pytest.raises(ValueError, match="included_evidence_ids"):
        EvidencePacket(
            packet_id="P1",
            research_question="q",
            as_of=_AS_OF,
            included_evidence_ids=("E1",),
            unknowns=("E1",),
            relation_assignments=(EvidenceRelationAssignment(evidence_id="E_GHOST", relation=EvidenceRelation.SUPPORTS),),
            relation_assignments_tracked=True,
        )


def test_conflicting_evidence_in_contradictory_bucket_without_assignment_is_allowed() -> None:
    """`contradictory_evidence`はAssignment Omission Checkの対象外(直交する別概念)。
    E1はrelation_assignments圏外のままcontradictory_evidenceに存在してもRejectされない
    (E2は通常通りAssignmentを持ち、Guard自体は正常に機能していることも合わせて確認する)。"""
    packet = EvidencePacket(
        packet_id="P1",
        research_question="q",
        as_of=_AS_OF,
        included_evidence_ids=("E1", "E2"),
        contradictory_evidence=("E1",),
        positive_evidence=("E2",),
        relation_assignments=(EvidenceRelationAssignment(evidence_id="E2", relation=EvidenceRelation.SUPPORTS),),
        relation_assignments_tracked=True,
    )
    assert "E1" not in {a.evidence_id for a in packet.relation_assignments}


# --- §8/§9/§11: Strong Final Bucket Partition Contract(Stage 3.15.3、D0092) -----------------


def test_ghost_id_in_bucket_is_rejected() -> None:
    with pytest.raises(ValueError, match="Ghost"):
        EvidencePacket(
            packet_id="P1",
            research_question="q",
            as_of=_AS_OF,
            included_evidence_ids=("E1",),
            positive_evidence=("E1", "E_GHOST"),
            unknowns=(),
            relation_assignments=(EvidenceRelationAssignment(evidence_id="E1", relation=EvidenceRelation.SUPPORTS),),
            relation_assignments_tracked=True,
        )


def test_same_id_in_positive_and_negative_is_rejected() -> None:
    with pytest.raises(ValueError, match="複数のFinal Bucket"):
        EvidencePacket(
            packet_id="P1",
            research_question="q",
            as_of=_AS_OF,
            included_evidence_ids=("E1",),
            positive_evidence=("E1",),
            negative_evidence=("E1",),
            relation_assignments=(EvidenceRelationAssignment(evidence_id="E1", relation=EvidenceRelation.SUPPORTS),),
            relation_assignments_tracked=True,
        )


def test_same_id_in_contradictory_and_positive_is_rejected() -> None:
    with pytest.raises(ValueError, match="複数のFinal Bucket"):
        EvidencePacket(
            packet_id="P1",
            research_question="q",
            as_of=_AS_OF,
            included_evidence_ids=("E1",),
            contradictory_evidence=("E1",),
            positive_evidence=("E1",),
            relation_assignments=(),
            relation_assignments_tracked=True,
        )


def test_bucket_internal_duplicate_is_rejected() -> None:
    with pytest.raises(ValueError, match="重複"):
        EvidencePacket(
            packet_id="P1",
            research_question="q",
            as_of=_AS_OF,
            included_evidence_ids=("E1",),
            positive_evidence=("E1", "E1"),
            relation_assignments=(EvidenceRelationAssignment(evidence_id="E1", relation=EvidenceRelation.SUPPORTS),),
            relation_assignments_tracked=True,
        )


def test_included_id_absent_from_all_buckets_is_rejected() -> None:
    with pytest.raises(ValueError, match="いずれのFinal Bucketにも分類"):
        EvidencePacket(
            packet_id="P1",
            research_question="q",
            as_of=_AS_OF,
            included_evidence_ids=("E1", "E2"),
            positive_evidence=("E1",),
            relation_assignments=(EvidenceRelationAssignment(evidence_id="E1", relation=EvidenceRelation.SUPPORTS),),
            relation_assignments_tracked=True,
        )


def test_supports_assignment_but_in_negative_bucket_is_rejected() -> None:
    with pytest.raises(ValueError, match="不整合"):
        EvidencePacket(
            packet_id="P1",
            research_question="q",
            as_of=_AS_OF,
            included_evidence_ids=("E1",),
            negative_evidence=("E1",),
            relation_assignments=(EvidenceRelationAssignment(evidence_id="E1", relation=EvidenceRelation.SUPPORTS),),
            relation_assignments_tracked=True,
        )


def test_neutral_assignment_but_in_positive_bucket_is_rejected() -> None:
    with pytest.raises(ValueError, match="不整合"):
        EvidencePacket(
            packet_id="P1",
            research_question="q",
            as_of=_AS_OF,
            included_evidence_ids=("E1",),
            positive_evidence=("E1",),
            relation_assignments=(EvidenceRelationAssignment(evidence_id="E1", relation=EvidenceRelation.NEUTRAL),),
            relation_assignments_tracked=True,
        )


def test_omitted_but_in_positive_bucket_is_rejected() -> None:
    with pytest.raises(ValueError, match="紛れ込んで"):
        EvidencePacket(
            packet_id="P1",
            research_question="q",
            as_of=_AS_OF,
            included_evidence_ids=("E1",),
            positive_evidence=("E1",),
            relation_assignments=(),
            relation_assignments_tracked=True,
        )


def test_supports_plus_conflicting_final_bucket_contradictory_only_passes() -> None:
    packet = EvidencePacket(
        packet_id="P1",
        research_question="q",
        as_of=_AS_OF,
        included_evidence_ids=("E1",),
        contradictory_evidence=("E1",),
        relation_assignments=(EvidenceRelationAssignment(evidence_id="E1", relation=EvidenceRelation.SUPPORTS),),
        relation_assignments_tracked=True,
    )
    assert packet.contradictory_evidence == ("E1",)
    assert packet.positive_evidence == ()


def test_neutral_plus_conflicting_final_bucket_contradictory_only_passes() -> None:
    packet = EvidencePacket(
        packet_id="P1",
        research_question="q",
        as_of=_AS_OF,
        included_evidence_ids=("E1",),
        contradictory_evidence=("E1",),
        relation_assignments=(EvidenceRelationAssignment(evidence_id="E1", relation=EvidenceRelation.NEUTRAL),),
        relation_assignments_tracked=True,
    )
    assert packet.contradictory_evidence == ("E1",)
    assert packet.unknowns == ()


def test_omitted_plus_conflicting_final_bucket_contradictory_only_passes() -> None:
    packet = EvidencePacket(
        packet_id="P1",
        research_question="q",
        as_of=_AS_OF,
        included_evidence_ids=("E1",),
        contradictory_evidence=("E1",),
        relation_assignments=(),
        relation_assignments_tracked=True,
    )
    assert packet.contradictory_evidence == ("E1",)


# --- §2-6: Tracking Marker(Stage 3.15.3、D0092、Finding A) ---------------------------------


def test_tracked_false_with_nonempty_assignments_is_rejected() -> None:
    with pytest.raises(ValueError, match="Tracking Marker不整合"):
        EvidencePacket(
            packet_id="P1",
            research_question="q",
            as_of=_AS_OF,
            included_evidence_ids=("E1",),
            positive_evidence=("E1",),
            relation_assignments=(EvidenceRelationAssignment(evidence_id="E1", relation=EvidenceRelation.SUPPORTS),),
            relation_assignments_tracked=False,
        )


def test_legacy_tracked_false_empty_assignments_is_allowed() -> None:
    packet = EvidencePacket(
        packet_id="P1",
        research_question="q",
        as_of=_AS_OF,
        included_evidence_ids=("E1",),
        positive_evidence=("E1",),
        relation_assignments=(),
        relation_assignments_tracked=False,
    )
    assert packet.relation_assignments_tracked is False
    assert packet.relation_assignments == ()


def test_tracked_true_all_omitted_is_allowed_and_distinguishable_from_legacy() -> None:
    """tracked=True + assignments=()(全EvidenceがOmitted)と、tracked=False +
    assignments=()(Legacy、Trackingという概念自体が無い)は、両方とも
    `relation_assignments == ()`だがMarkerで区別できる(Finding A)。"""
    tracked_all_omitted = EvidencePacket(
        packet_id="P1",
        research_question="q",
        as_of=_AS_OF,
        included_evidence_ids=("E1",),
        unknowns=("E1",),
        relation_assignments=(),
        relation_assignments_tracked=True,
    )
    legacy = EvidencePacket(
        packet_id="P2",
        research_question="q",
        as_of=_AS_OF,
        included_evidence_ids=("E1",),
        positive_evidence=("E1",),
        relation_assignments=(),
        relation_assignments_tracked=False,
    )
    assert tracked_all_omitted.relation_assignments == legacy.relation_assignments == ()
    assert tracked_all_omitted.relation_assignments_tracked is True
    assert legacy.relation_assignments_tracked is False


def test_build_evidence_packet_always_sets_tracked_true() -> None:
    e1 = _evidence("E1")
    packet = build_evidence_packet(
        packet_id="P1",
        research_question="q",
        as_of=_AS_OF,
        evidence_pool=[e1],
        relations={},
    )
    assert packet.relation_assignments_tracked is True
    assert packet.relation_assignments == ()
    assert packet.unknowns == ("E1",)


# --- §32: Backward Compatibility(Legacy Packet) --------------------------------------------


def test_legacy_packet_with_empty_relation_assignments_skips_consistency_guard() -> None:
    """relation_assignments=()(既定)は、Bucketが何であってもGuardを実行しない
    (既存呼び出し・既存Testとの後方互換)。"""
    packet = EvidencePacket(
        packet_id="P1",
        research_question="q",
        as_of=_AS_OF,
        included_evidence_ids=("E1",),
        positive_evidence=("E1",),  # relation_assignmentsが無くても許容される
    )
    assert packet.relation_assignments == ()
    assert packet.positive_evidence == ("E1",)
