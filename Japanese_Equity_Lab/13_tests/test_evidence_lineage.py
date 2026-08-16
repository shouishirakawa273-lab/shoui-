"""Phase3D(D0040): Raw -> Normalized -> Derived -> EvidencePacket -> DecisionEvidenceLog の
lineageが、既存`lib.registry.provenance.ProvenanceStore`(Phase1.1〜)で
そのまま追跡できることを確認する(新しいProvenance機構は作らない)。

あわせて、EvidencePacketに含まれる全Evidenceがsourceまで遡れること(要件9)、
Source Authorityが最後まで保持されること(要件8)も確認する。
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from lib.evidence.model import AiDerivedProvenance, DataLayer, EvidenceRecord, EvidenceRelation, EvidenceType
from lib.evidence.packet import build_evidence_packet
from lib.registry.provenance import ProvenanceLink, ProvenanceStore
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


def test_raw_to_normalized_to_derived_to_packet_lineage_is_traceable(tmp_path: Path) -> None:
    store = ProvenanceStore(tmp_path / "provenance.jsonl")

    raw_id, normalized_id, derived_id, packet_id, decision_log_id = (
        "RAW_SNAP_1",
        "E_NORMALIZED_1",
        "E_DERIVED_1",
        "PACKET_1",
        "DLOG_1",
    )

    normalized = EvidenceRecord(
        evidence_id=normalized_id,
        evidence_type=EvidenceType.FACT,
        layer=DataLayer.NORMALIZED,
        capability=DataCapability.DISCLOSURE,
        content="会社予想営業利益を100億→120億へ修正",
        source=_source(),
    )
    derived = EvidenceRecord(
        evidence_id=derived_id,
        evidence_type=EvidenceType.INTERPRETATION,
        layer=DataLayer.DERIVED,
        capability=DataCapability.DISCLOSURE,
        content="上方修正の要約",
        source=_source(),
        ai_derived_provenance=AiDerivedProvenance(
            model_provider="anthropic",
            model_name="test-model",
            input_evidence_ids=(normalized_id,),
            generated_at=datetime(2024, 6, 1, tzinfo=UTC),
        ),
    )
    packet = build_evidence_packet(
        packet_id=packet_id,
        research_question="上方修正は構造的か一時的か",
        as_of=_AS_OF,
        evidence_pool=[normalized, derived],
        relations={normalized_id: EvidenceRelation.SUPPORTS, derived_id: EvidenceRelation.SUPPORTS},
    )

    store.add_link(
        ProvenanceLink(link_id="L1", from_type="raw_snapshot", from_id=raw_id, to_type="normalized_evidence", to_id=normalized_id)
    )
    store.add_link(
        ProvenanceLink(
            link_id="L2", from_type="normalized_evidence", from_id=normalized_id, to_type="derived_evidence", to_id=derived_id
        )
    )
    store.add_link(
        ProvenanceLink(
            link_id="L3", from_type="derived_evidence", from_id=derived_id, to_type="evidence_packet", to_id=packet.packet_id
        )
    )
    store.add_link(
        ProvenanceLink(
            link_id="L4",
            from_type="evidence_packet",
            from_id=packet.packet_id,
            to_type="decision_evidence_log",
            to_id=decision_log_id,
        )
    )

    chain = store.trace_to_origin("decision_evidence_log", decision_log_id)
    assert [link.from_type for link in chain] == ["raw_snapshot", "normalized_evidence", "derived_evidence", "evidence_packet"]
    assert chain[0].from_id == raw_id
    assert chain[-1].to_id == decision_log_id


def test_all_evidence_in_packet_traces_back_to_source_metadata() -> None:
    """要件9: EvidencePacketのincluded evidenceが全件Provenanceへ(=Sourceまで)遡れる。"""
    e1 = EvidenceRecord(
        evidence_id="E1",
        evidence_type=EvidenceType.FACT,
        layer=DataLayer.NORMALIZED,
        capability=DataCapability.DISCLOSURE,
        content="内容1",
        source=_source(),
    )
    e2 = EvidenceRecord(
        evidence_id="E2",
        evidence_type=EvidenceType.OPINION,
        layer=DataLayer.NORMALIZED,
        capability=DataCapability.IDEA,
        content="内容2",
        source=_source(),
    )
    pool = [e1, e2]
    packet = build_evidence_packet(
        packet_id="P1", research_question="q", as_of=_AS_OF, evidence_pool=pool, relations={"E1": EvidenceRelation.SUPPORTS}
    )
    by_id = {e.evidence_id: e for e in pool}
    for evidence_id in packet.included_evidence_ids:
        evidence = by_id[evidence_id]
        assert evidence.source.source_id  # sourceまで遡れる(未設定=空文字ではない)
        assert evidence.source.available_at is not None


# --- Test 8: Source Authorityが保持される ---


def test_source_authority_class_survives_through_evidence_and_packet() -> None:
    e1 = EvidenceRecord(
        evidence_id="E1",
        evidence_type=EvidenceType.FACT,
        layer=DataLayer.NORMALIZED,
        capability=DataCapability.DISCLOSURE,
        content="内容",
        source=_source(),
    )
    assert e1.source.source_authority_class == SourceAuthorityClass.PRIMARY_OFFICIAL

    packet = build_evidence_packet(
        packet_id="P1", research_question="q", as_of=_AS_OF, evidence_pool=[e1], relations={"E1": EvidenceRelation.SUPPORTS}
    )
    # Packetはevidence_idの参照のみを持つ(Authority Class自体はEvidenceRecord側にそのまま残る、
    # Packet構築時にAuthorityを要約・破棄しない)。
    assert e1.evidence_id in packet.positive_evidence
    assert e1.source.source_authority_class == SourceAuthorityClass.PRIMARY_OFFICIAL
