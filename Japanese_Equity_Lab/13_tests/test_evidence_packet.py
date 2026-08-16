"""Phase3D(D0040): EvidencePacket + Anti-Confirmation Guardrailsのテスト。

DEFAULT STANCE = DISCONFIRM, NOT CONFIRM。情報件数の多数決を禁止し、
Evidence不足を無理にPositive/Negativeへ分類しない。
"""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime

import pytest
from lib.evidence.model import DataLayer, EvidenceRecord, EvidenceRelation, EvidenceType
from lib.evidence.packet import EvidencePacket, build_evidence_packet
from lib.sources.catalog import DataCapability, PrimaryOrSecondary, SourceAuthorityClass, SourceMetadata

_AS_OF = datetime(2024, 6, 1, tzinfo=UTC)


def _source(authority: SourceAuthorityClass) -> SourceMetadata:
    return SourceMetadata(
        source_id="s1",
        source_type="TDNET",
        provider_name="TDnet",
        source_authority_class=authority,
        primary_or_secondary=PrimaryOrSecondary.PRIMARY,
        retrieved_at=datetime(2024, 1, 1, tzinfo=UTC),
        published_at=datetime(2024, 1, 1, tzinfo=UTC),
        available_at=datetime(2024, 1, 1, tzinfo=UTC),
    )


def _evidence(
    evidence_id: str, evidence_type: EvidenceType, authority: SourceAuthorityClass, content: str = "内容"
) -> EvidenceRecord:
    return EvidenceRecord(
        evidence_id=evidence_id,
        evidence_type=evidence_type,
        layer=DataLayer.NORMALIZED,
        capability=DataCapability.DISCLOSURE,
        content=content,
        source=_source(authority),
    )


# --- Test 10: Missing Evidenceをゼロ/Neutralとして扱わずUNKNOWNとする ---


def test_evidence_without_assigned_relation_goes_to_unknowns_not_dropped() -> None:
    e1 = _evidence("E1", EvidenceType.FACT, SourceAuthorityClass.PRIMARY_OFFICIAL)
    packet = build_evidence_packet(
        packet_id="P1",
        research_question="q",
        as_of=_AS_OF,
        evidence_pool=[e1],
        relations={},  # 誰も判定していない
    )
    assert packet.unknowns == ("E1",)
    assert packet.positive_evidence == ()
    assert packet.negative_evidence == ()
    assert "E1" in packet.included_evidence_ids  # 黙って除外しない


# --- Anti-confirmation A: Positive Evidenceしか無いFixtureでもmissing_negative_search等を表現できる ---


def test_all_positive_evidence_can_still_flag_missing_negative_search() -> None:
    e1 = _evidence("E1", EvidenceType.FACT, SourceAuthorityClass.PRIMARY_OFFICIAL, "好材料のFACT")
    packet = build_evidence_packet(
        packet_id="P1",
        research_question="q",
        as_of=_AS_OF,
        evidence_pool=[e1],
        relations={"E1": EvidenceRelation.SUPPORTS},
        missing_expected_sources=("NEGATIVE_SEARCH_NOT_PERFORMED", "COMPETITOR_DISCLOSURE_NOT_CHECKED"),
    )
    assert packet.positive_evidence == ("E1",)
    assert packet.negative_evidence == ()
    # 反証探索を行っていないこと自体が、Schema上明示的に残る(隠さない)。
    assert "NEGATIVE_SEARCH_NOT_PERFORMED" in packet.missing_expected_sources


# --- Anti-confirmation B: 情報件数の多数決を禁止する ---


def test_ten_social_opinions_do_not_override_single_primary_fact() -> None:
    """SNS 10件がSUPPORTSでも、Primary Official Fact 1件のCONTRADICTSは消えない
    (件数による上書きロジックがこのモジュールに存在しないことを直接確認する)。"""
    social_opinions = [_evidence(f"OPINION_{i}", EvidenceType.OPINION, SourceAuthorityClass.SOCIAL) for i in range(10)]
    primary_fact = _evidence("FACT_1", EvidenceType.FACT, SourceAuthorityClass.PRIMARY_OFFICIAL, "会社予想を下方修正")

    relations = {opinion.evidence_id: EvidenceRelation.SUPPORTS for opinion in social_opinions}
    relations["FACT_1"] = EvidenceRelation.CONTRADICTS

    packet = build_evidence_packet(
        packet_id="P1",
        research_question="q",
        as_of=_AS_OF,
        evidence_pool=[*social_opinions, primary_fact],
        relations=relations,
    )
    assert len(packet.positive_evidence) == 10
    assert packet.negative_evidence == ("FACT_1",)  # 10対1でも消えない・上書きされない


def test_evidence_packet_has_no_overall_verdict_field() -> None:
    """多数決やAuto-Promotionが紛れ込む余地を構造的に無くすため、
    EvidencePacketにConclusion/Verdict/Supportedに相当するFieldが存在しないことを確認する。"""
    field_names = {f.name for f in dataclasses.fields(EvidencePacket)}
    forbidden = {"verdict", "conclusion", "supported", "is_supported", "overall_stance", "recommendation"}
    assert field_names.isdisjoint(forbidden)


# --- Anti-confirmation C: Conflicting Sourcesを自動統合せず、CONFLICTとして保持する ---


def test_conflicting_sources_are_preserved_as_contradictory_not_auto_resolved() -> None:
    fact_a = _evidence("FACT_A", EvidenceType.FACT, SourceAuthorityClass.PRIMARY_OFFICIAL, "上方修正")
    fact_b = _evidence("FACT_B", EvidenceType.FACT, SourceAuthorityClass.COMPANY_PRIMARY, "下方修正(別Sourceの矛盾する報告)")
    packet = build_evidence_packet(
        packet_id="P1",
        research_question="q",
        as_of=_AS_OF,
        evidence_pool=[fact_a, fact_b],
        relations={"FACT_A": EvidenceRelation.SUPPORTS, "FACT_B": EvidenceRelation.CONTRADICTS},
        conflicting_evidence_ids=["FACT_A", "FACT_B"],
    )
    assert set(packet.contradictory_evidence) == {"FACT_A", "FACT_B"}
    # 対立指定を優先するため、positive/negativeのどちらか一方へは自動的に割り振られない。
    assert packet.positive_evidence == ()
    assert packet.negative_evidence == ()


# --- Anti-confirmation D: Evidence不足の場合、自動昇格しない ---


def test_insufficient_evidence_does_not_auto_promote_to_supported() -> None:
    packet = build_evidence_packet(
        packet_id="P1",
        research_question="q",
        as_of=_AS_OF,
        evidence_pool=[],
        relations={},
        missing_expected_sources=("EARNINGS_NOT_YET_RELEASED",),
    )
    assert packet.positive_evidence == ()
    assert packet.negative_evidence == ()
    assert packet.unknowns == ()
    # 「昇格させる」ためのAPI/Fieldがそもそも存在しない(上のno-verdict-fieldテストと合わせて確認)。


# --- Schemaの整合性チェック ---


def test_build_evidence_packet_rejects_relation_for_unknown_evidence_id() -> None:
    with pytest.raises(ValueError, match="E_MISSING"):
        build_evidence_packet(
            packet_id="P1",
            research_question="q",
            as_of=_AS_OF,
            evidence_pool=[],
            relations={"E_MISSING": EvidenceRelation.SUPPORTS},
        )


def test_evidence_packet_requires_tz_aware_as_of() -> None:
    with pytest.raises(ValueError, match="tz-aware"):
        EvidencePacket(packet_id="P1", research_question="q", as_of=datetime(2024, 1, 1))


def test_alternative_explanation_relation_is_tracked_separately_from_supports_and_contradicts() -> None:
    e1 = _evidence("E1", EvidenceType.INTERPRETATION, SourceAuthorityClass.SECONDARY, "別の要因が主因との分析")
    packet = build_evidence_packet(
        packet_id="P1",
        research_question="q",
        as_of=_AS_OF,
        evidence_pool=[e1],
        relations={"E1": EvidenceRelation.ALTERNATIVE_EXPLANATION},
    )
    assert packet.alternative_explanation_evidence == ("E1",)
    assert packet.positive_evidence == ()
    assert packet.negative_evidence == ()
