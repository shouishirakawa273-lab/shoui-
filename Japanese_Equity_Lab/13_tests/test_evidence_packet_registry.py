"""EvidencePacketRegistry(Stage 3.15.2、D0091): `EvidencePacket`
(`relation_assignments`含む)をLosslessに永続化・Fresh Process再解決
できることを検証する。
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from lib.errors import AppendOnlyViolationError
from lib.evidence.model import DataLayer, EvidenceRecord, EvidenceRelation, EvidenceType
from lib.evidence.packet import EvidencePacket, EvidenceRelationAssignment, build_evidence_packet
from lib.registry.evidence_packet_registry import EvidencePacketRegistry
from lib.sources.catalog import DataCapability, PrimaryOrSecondary, SourceAuthorityClass, SourceMetadata

_AS_OF = datetime(2024, 6, 1, tzinfo=UTC)


def _full_packet(packet_id: str = "P1") -> EvidencePacket:
    return EvidencePacket(
        packet_id=packet_id,
        research_question="7203の妥当性は?",
        as_of=_AS_OF,
        included_evidence_ids=("A", "B", "C", "D"),
        excluded_candidate_sources=("PEER_UNIVERSE",),
        retrieval_reason="RetrievalPlan(included=['VALUATION'])",
        missing_expected_sources=("CONSENSUS",),
        positive_evidence=("D",),
        negative_evidence=(),
        alternative_explanation_evidence=(),
        contradictory_evidence=(),
        unknowns=("A", "B", "C"),
        provenance_id="PROV_1",
        relation_assignments=(
            EvidenceRelationAssignment(evidence_id="A", relation=EvidenceRelation.NEUTRAL),
            EvidenceRelationAssignment(evidence_id="B", relation=EvidenceRelation.UNKNOWN),
            EvidenceRelationAssignment(evidence_id="D", relation=EvidenceRelation.SUPPORTS),
            # Cは意図的にOmitted(relation_assignmentsに含めない)
        ),
    )


def test_record_and_get(tmp_path: Path) -> None:
    registry = EvidencePacketRegistry(tmp_path / "packets.jsonl")
    packet = _full_packet()
    registry.record(packet)
    resolved = registry.get(packet.packet_id)
    assert resolved is not None
    assert resolved.packet_id == packet.packet_id


def test_get_returns_none_for_unknown_id(tmp_path: Path) -> None:
    registry = EvidencePacketRegistry(tmp_path / "packets.jsonl")
    assert registry.get("P_UNKNOWN") is None


def test_require_raises_for_unknown_id(tmp_path: Path) -> None:
    registry = EvidencePacketRegistry(tmp_path / "packets.jsonl")
    with pytest.raises(KeyError):
        registry.require("P_UNKNOWN")


def test_all_returns_every_recorded_packet(tmp_path: Path) -> None:
    registry = EvidencePacketRegistry(tmp_path / "packets.jsonl")
    registry.record(_full_packet("P_A"))
    registry.record(_full_packet("P_B"))
    ids = {p.packet_id for p in registry.all()}
    assert ids == {"P_A", "P_B"}


def test_fresh_instance_reload_resolves_identical_packet(tmp_path: Path) -> None:
    path = tmp_path / "packets.jsonl"
    registry_a = EvidencePacketRegistry(path)
    packet = _full_packet()
    registry_a.record(packet)

    registry_b = EvidencePacketRegistry(path)
    resolved = registry_b.require(packet.packet_id)
    assert resolved == packet


def test_datetime_timezone_round_trips(tmp_path: Path) -> None:
    registry = EvidencePacketRegistry(tmp_path / "packets.jsonl")
    packet = _full_packet()
    registry.record(packet)
    resolved = registry.require(packet.packet_id)
    assert resolved.as_of == packet.as_of
    assert resolved.as_of.tzinfo is not None


def test_relation_assignments_enum_and_tuple_round_trip(tmp_path: Path) -> None:
    registry = EvidencePacketRegistry(tmp_path / "packets.jsonl")
    packet = _full_packet()
    registry.record(packet)
    resolved = registry.require(packet.packet_id)

    assert isinstance(resolved.relation_assignments, tuple)
    by_id = {a.evidence_id: a.relation for a in resolved.relation_assignments}
    assert by_id["A"] is EvidenceRelation.NEUTRAL
    assert by_id["B"] is EvidenceRelation.UNKNOWN
    assert by_id["D"] is EvidenceRelation.SUPPORTS
    assert "C" not in by_id  # Omittedのまま復元される(NEUTRAL/UNKNOWNへ化けない)
    assert isinstance(by_id["A"], EvidenceRelation)


def test_other_tuple_fields_round_trip_as_tuple(tmp_path: Path) -> None:
    registry = EvidencePacketRegistry(tmp_path / "packets.jsonl")
    packet = _full_packet()
    registry.record(packet)
    resolved = registry.require(packet.packet_id)
    assert isinstance(resolved.included_evidence_ids, tuple)
    assert isinstance(resolved.unknowns, tuple)
    assert resolved.included_evidence_ids == packet.included_evidence_ids


def test_legacy_packet_with_empty_relation_assignments_round_trips(tmp_path: Path) -> None:
    registry = EvidencePacketRegistry(tmp_path / "packets.jsonl")
    legacy = EvidencePacket(
        packet_id="P_LEGACY",
        research_question="q",
        as_of=_AS_OF,
        included_evidence_ids=("E1",),
        positive_evidence=("E1",),
    )
    registry.record(legacy)
    resolved = registry.require("P_LEGACY")
    assert resolved.relation_assignments == ()
    assert resolved.positive_evidence == ("E1",)


def test_full_packet_semantic_equality_after_round_trip(tmp_path: Path) -> None:
    registry = EvidencePacketRegistry(tmp_path / "packets.jsonl")
    packet = _full_packet()
    registry.record(packet)
    resolved = registry.require(packet.packet_id)
    assert resolved == packet


def test_duplicate_packet_id_is_rejected(tmp_path: Path) -> None:
    registry = EvidencePacketRegistry(tmp_path / "packets.jsonl")
    packet = _full_packet()
    registry.record(packet)
    with pytest.raises(AppendOnlyViolationError):
        registry.record(packet)


def test_duplicate_packet_id_with_different_payload_is_also_rejected(tmp_path: Path) -> None:
    registry = EvidencePacketRegistry(tmp_path / "packets.jsonl")
    registry.record(_full_packet("P_SAME"))
    different = EvidencePacket(packet_id="P_SAME", research_question="different", as_of=_AS_OF)
    with pytest.raises(AppendOnlyViolationError):
        registry.record(different)


# --- Required Regression A/B/C/D(D0091 Critical Fix、Conflict Override後のReload) ---


def _tiny_evidence(evidence_id: str) -> EvidenceRecord:
    return EvidenceRecord(
        evidence_id=evidence_id,
        evidence_type=EvidenceType.FACT,
        layer=DataLayer.NORMALIZED,
        capability=DataCapability.DISCLOSURE,
        content="内容",
        source=SourceMetadata(
            source_id="s1",
            source_type="TDNET",
            provider_name="TDnet",
            source_authority_class=SourceAuthorityClass.PRIMARY_OFFICIAL,
            primary_or_secondary=PrimaryOrSecondary.PRIMARY,
            retrieved_at=datetime(2024, 1, 1, tzinfo=UTC),
            published_at=datetime(2024, 1, 1, tzinfo=UTC),
            available_at=datetime(2024, 1, 1, tzinfo=UTC),
        ),
    )


def test_regression_a_conflicting_supports_survives_reload(tmp_path: Path) -> None:
    e1 = _tiny_evidence("E1")
    packet = build_evidence_packet(
        packet_id="P_REGRESSION_A",
        research_question="q",
        as_of=_AS_OF,
        evidence_pool=[e1],
        relations={"E1": EvidenceRelation.SUPPORTS},
        conflicting_evidence_ids=["E1"],
    )
    registry = EvidencePacketRegistry(tmp_path / "packets.jsonl")
    registry.record(packet)
    reloaded = EvidencePacketRegistry(tmp_path / "packets.jsonl").require("P_REGRESSION_A")

    by_id = {a.evidence_id: a.relation for a in reloaded.relation_assignments}
    assert by_id["E1"] == EvidenceRelation.SUPPORTS
    assert "E1" in reloaded.contradictory_evidence
    assert "E1" not in reloaded.positive_evidence


def test_regression_b_conflicting_neutral_survives_reload(tmp_path: Path) -> None:
    e1 = _tiny_evidence("E1")
    packet = build_evidence_packet(
        packet_id="P_REGRESSION_B",
        research_question="q",
        as_of=_AS_OF,
        evidence_pool=[e1],
        relations={"E1": EvidenceRelation.NEUTRAL},
        conflicting_evidence_ids=["E1"],
    )
    registry = EvidencePacketRegistry(tmp_path / "packets.jsonl")
    registry.record(packet)
    reloaded = EvidencePacketRegistry(tmp_path / "packets.jsonl").require("P_REGRESSION_B")

    by_id = {a.evidence_id: a.relation for a in reloaded.relation_assignments}
    assert by_id["E1"] == EvidenceRelation.NEUTRAL
    assert "E1" in reloaded.contradictory_evidence
    assert "E1" not in reloaded.unknowns


def test_regression_c_conflicting_without_relation_has_no_assignment_after_reload(tmp_path: Path) -> None:
    e1 = _tiny_evidence("E1")
    packet = build_evidence_packet(
        packet_id="P_REGRESSION_C",
        research_question="q",
        as_of=_AS_OF,
        evidence_pool=[e1],
        relations={},
        conflicting_evidence_ids=["E1"],
    )
    registry = EvidencePacketRegistry(tmp_path / "packets.jsonl")
    registry.record(packet)
    reloaded = EvidencePacketRegistry(tmp_path / "packets.jsonl").require("P_REGRESSION_C")

    assigned_ids = {a.evidence_id for a in reloaded.relation_assignments}
    assert "E1" not in assigned_ids
    assert "E1" in reloaded.contradictory_evidence


def test_regression_d_explicit_unknown_vs_omitted_vs_neutral_distinguishable_after_reload(tmp_path: Path) -> None:
    a, b, c = _tiny_evidence("A"), _tiny_evidence("B"), _tiny_evidence("C")
    packet = build_evidence_packet(
        packet_id="P_REGRESSION_D",
        research_question="q",
        as_of=_AS_OF,
        evidence_pool=[a, b, c],
        relations={"A": EvidenceRelation.NEUTRAL, "B": EvidenceRelation.UNKNOWN},  # Cは省略
    )
    registry = EvidencePacketRegistry(tmp_path / "packets.jsonl")
    registry.record(packet)
    reloaded = EvidencePacketRegistry(tmp_path / "packets.jsonl").require("P_REGRESSION_D")

    by_id = {a_.evidence_id: a_.relation for a_ in reloaded.relation_assignments}
    assert by_id["A"] == EvidenceRelation.NEUTRAL
    assert by_id["B"] == EvidenceRelation.UNKNOWN
    assert "C" not in by_id
    assert set(reloaded.unknowns) == {"A", "B", "C"}  # Bucket上は3件とも収束(既存挙動)


def test_malformed_json_line_fails_closed(tmp_path: Path) -> None:
    path = tmp_path / "packets.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not valid json\n", encoding="utf-8")
    registry = EvidencePacketRegistry(path)
    with pytest.raises(Exception):  # noqa: B017 - 既存Registry群と同じ、json.loadsをそのまま伝播
        registry.all()
