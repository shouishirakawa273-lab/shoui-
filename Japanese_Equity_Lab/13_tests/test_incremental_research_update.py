"""`lib.evidence.incremental_update`(D0105)のRegression Test。

`build_incremental_research_update()`が以下を機械的に強制することを
検証する:

1. Evidence Delta(NEW/UNCHANGED/REMOVED_OR_MISSING/POTENTIALLY_
   SUPERSEDED)が、Text類似度・Embedding・LLM Matchingを一切使わず、
   `EvidenceRecord.evidence_id`の構造的Equalityと既存の明示的
   Relationship Field(`SemanticClaim.supersedes_claim_id`)のみで
   決定論的に計算されること。
2. Supersessionは明示的Keyが無い限り一切推測しないこと(同じ文言・
   同じ会社・反対方向・単なる後日付のいずれも不十分)。
3. Research Impact MappingがResearchArtifact.included_evidence_ids
   (既存Field)のみを使い、NEW Evidence単独では既存Research Nodeを
   無条件にREVIEW_REQUIREDにしないこと。
4. ResearchArtifact/NarrativeCaseを一切Mutateしないこと。
5. Model呼び出しが無いこと(Source Level確認)。
6. 入力順序に対してOutputが決定論的であること。

Fixture方式は`test_disclosures_evidence_lineage.py`と同じ(Synthetic
EDINET-shaped ZIPを構築し、`normalize_edinet_type1_zip()`経由で実
`EvidenceSpan`を得る)。
"""

from __future__ import annotations

import ast
import io
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import pytest
from lib.disclosures.candidate_extraction import SemanticClaimCandidate
from lib.disclosures.evidence_integration import integrate_accepted_semantic_claim
from lib.disclosures.model import DisclosureDocument
from lib.disclosures.normalization import NormalizedDisclosureDocument, normalize_edinet_type1_zip
from lib.disclosures.semantic_claims import (
    ClaimDirection,
    EvidenceSpan,
    FaithfulnessOutcome,
    SemanticClaim,
    SemanticClaimType,
    build_semantic_claim,
)
from lib.evidence import incremental_update as incremental_update_module
from lib.evidence.incremental_update import (
    EvidenceDeltaStatus,
    IncrementalResearchUpdateResult,
    IncrementalResearchUpdateSchemaError,
    ResearchImpactStatus,
    build_incremental_research_update,
)
from lib.evidence.model import AiDerivedProvenance, AvailabilityBasis, EvidenceRecord
from lib.evidence.research_artifact import ConfidenceLevel, NarrativeCase, ResearchArtifact, ResearchConclusion
from lib.sources.catalog import SourceAuthorityClass

_XHTML_OPEN = '<html xmlns="http://www.w3.org/1999/xhtml" xmlns:ix="http://www.xbrl.org/2008/inlineXBRL">'


def _htm(body_inner: str) -> bytes:
    return (f'<?xml version="1.0" encoding="UTF-8"?>{_XHTML_OPEN}<head></head><body>{body_inner}</body></html>').encode()


def _ix(name: str, inner: str) -> str:
    return f'<ix:nonNumeric name="{name}">{inner}</ix:nonNumeric>'


def _build_zip(entries: dict[str, bytes], *, date_time: tuple[int, int, int, int, int, int] = (2026, 1, 1, 0, 0, 0)) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, content in entries.items():
            info = zipfile.ZipInfo(filename=name, date_time=date_time)
            info.compress_type = zipfile.ZIP_DEFLATED
            zf.writestr(info, content)
    return buf.getvalue()


_BODY_PATH = "XBRL/PublicDoc/0101010_honbun_test_ixbrl.htm"


def _single_member_doc(body_inner: str, *, document_id: str = "DOC1") -> NormalizedDisclosureDocument:
    raw_zip = _build_zip({_BODY_PATH: _htm(body_inner)})
    return normalize_edinet_type1_zip(document_id=document_id, raw_zip_bytes=raw_zip)


def _span_for(doc: NormalizedDisclosureDocument, *, occurrence: int = 0) -> EvidenceSpan:
    member = doc.members[0]
    return EvidenceSpan.from_text_block(document=doc, member=member, text_block=member.text_blocks[occurrence])


def _provenance(*, generated_at: datetime = datetime(2026, 1, 1, tzinfo=UTC)) -> AiDerivedProvenance:
    return AiDerivedProvenance(
        model_provider="test-provider", model_name="test-model", model_version="v1", generated_at=generated_at
    )


def _candidate(
    *,
    evidence_span: EvidenceSpan,
    claim_type: SemanticClaimType = SemanticClaimType.BUSINESS_RISK,
    normalized_claim_text: str = "重要な変更はありません。",
    direction: ClaimDirection = ClaimDirection.UNSPECIFIED,
    extraction_version: str = "EXTRACT_V1",
) -> SemanticClaimCandidate:
    return SemanticClaimCandidate(
        claim_type=claim_type,
        normalized_claim_text=normalized_claim_text,
        direction=direction,
        evidence_span=evidence_span,
        extraction_version=extraction_version,
        extraction_provenance=_provenance(),
    )


def _claim_from_candidate(
    candidate: SemanticClaimCandidate,
    *,
    faithfulness_outcome: FaithfulnessOutcome = FaithfulnessOutcome.ACCEPT,
    supersedes_claim_id: str | None = None,
) -> SemanticClaim:
    return build_semantic_claim(
        claim_type=candidate.claim_type,
        normalized_claim_text=candidate.normalized_claim_text,
        direction=candidate.direction,
        evidence_span=candidate.evidence_span,
        faithfulness_outcome=faithfulness_outcome,
        extraction_version=candidate.extraction_version,
        schema_version=candidate.schema_version,
        extraction_provenance=candidate.extraction_provenance,
        supersedes_claim_id=supersedes_claim_id,
    )


def _disclosure_document(
    *,
    internal_document_id: str = "DOC1",
    entity_id: str | None = "7203",
    provider_available_at: datetime | None = None,
    provider_available_at_basis: AvailabilityBasis = AvailabilityBasis.UNKNOWN,
    retrieved_at: datetime = datetime(2026, 8, 17, 15, 6, tzinfo=UTC),
    provenance_id: str | None = None,
) -> DisclosureDocument:
    return DisclosureDocument(
        internal_document_id=internal_document_id,
        source_document_id="S1",
        entity_id=entity_id,
        title="半期報告書",
        originating_source="EDINET",
        delivery_provider="EDINET",
        provider_available_at=provider_available_at,
        provider_available_at_basis=provider_available_at_basis,
        retrieved_at=retrieved_at,
        provenance_id=provenance_id,
    )


def _evidence_for(claim: SemanticClaim, document: DisclosureDocument) -> EvidenceRecord:
    result = integrate_accepted_semantic_claim(
        claim=claim, document=document, source_authority_class=SourceAuthorityClass.PRIMARY_OFFICIAL
    )
    assert result.evidence is not None
    return result.evidence


def _research_artifact(artifact_id: str, included_evidence_ids: tuple[str, ...]) -> ResearchArtifact:
    conclusion = ResearchConclusion.SUPPORTED if included_evidence_ids else ResearchConclusion.INSUFFICIENT_EVIDENCE
    confidence = ConfidenceLevel.MEDIUM if included_evidence_ids else ConfidenceLevel.INSUFFICIENT
    return ResearchArtifact(
        artifact_id=artifact_id,
        entity_code="7203",
        as_of=datetime(2026, 8, 20, tzinfo=UTC),
        research_question_id="RQ_TEST_0001",
        evidence_packet_id=f"PKT_{artifact_id}",
        bull_case=NarrativeCase(summary="Bull"),
        base_case=NarrativeCase(summary="Base"),
        bear_case=NarrativeCase(summary="Bear"),
        data_confidence=confidence,
        evidence_confidence=confidence,
        research_confidence=confidence,
        conclusion=conclusion,
        conclusion_rationale="test fixture",
        included_evidence_ids=included_evidence_ids,
    )


def _build_evidence(
    *,
    document_id: str = "DOC1",
    text: str = "重要な変更はありません。",
    occurrence: int = 0,
    extraction_version: str = "EXTRACT_V1",
    direction: ClaimDirection = ClaimDirection.UNSPECIFIED,
    provider_available_at: datetime | None = None,
    retrieved_at: datetime = datetime(2026, 8, 17, 15, 6, tzinfo=UTC),
    supersedes_claim_id: str | None = None,
    body_extra: str = "",
) -> tuple[EvidenceRecord, SemanticClaim, SemanticClaimCandidate, NormalizedDisclosureDocument, DisclosureDocument]:
    """1件のEvidenceRecordを、実際のD0101.1/D0102.x/D0103経路で構築する。"""
    body = _ix("jpcrp_cor:BusinessRisksTextBlock", text) + body_extra
    norm_doc = _single_member_doc(body, document_id=document_id)
    span = _span_for(norm_doc, occurrence=occurrence)
    candidate = _candidate(
        evidence_span=span, normalized_claim_text=text, direction=direction, extraction_version=extraction_version
    )
    claim = _claim_from_candidate(candidate, supersedes_claim_id=supersedes_claim_id)
    document = _disclosure_document(
        internal_document_id=document_id, provider_available_at=provider_available_at, retrieved_at=retrieved_at
    )
    evidence = _evidence_for(claim, document)
    return evidence, claim, candidate, norm_doc, document


# ============================================================
# §19: Forward Update Scenario
# ============================================================


def test_forward_update_scenario() -> None:
    e1, c1, _, _, _ = _build_evidence(document_id="DOC_Q1", text="E1クレーム。")
    e2, c2, _, _, _ = _build_evidence(document_id="DOC_Q1", text="E2クレーム。")
    e3, c3, _, _, _ = _build_evidence(document_id="DOC_Q1", text="E3クレーム。")
    e4, c4, _, _, _ = _build_evidence(document_id="DOC_Q2", text="E4クレーム。")

    r1 = _research_artifact("R1", (e1.evidence_id, e3.evidence_id))
    r2 = _research_artifact("R2", (e2.evidence_id,))

    result = build_incremental_research_update(
        prior_evidence_records=(e1, e2, e3),
        current_evidence_records=(e1, e2, e4),
        research_artifacts=(r1, r2),
        semantic_claims=(c1, c2, c3, c4),
    )

    assert result.status == EvidenceDeltaStatus.SUCCESS
    assert result.unchanged_evidence_ids == tuple(sorted((e1.evidence_id, e2.evidence_id)))
    assert result.removed_or_missing_evidence_ids == (e3.evidence_id,)
    assert result.new_evidence_ids == (e4.evidence_id,)
    assert result.unassigned_new_evidence_ids == (e4.evidence_id,)

    nodes = {n.artifact_id: n for n in result.affected_research_nodes}
    assert nodes["R1"].status == ResearchImpactStatus.REVIEW_REQUIRED
    assert e3.evidence_id in nodes["R1"].affected_evidence_ids
    assert nodes["R2"].status == ResearchImpactStatus.UNAFFECTED


# ============================================================
# §20: Re-Extraction Scenario(D0104.1 Case)
# ============================================================


def test_re_extraction_under_new_version_does_not_collapse_into_old_evidence() -> None:
    """同一TextBlockが新しいextraction_versionで再Extractionされても、
    結果のEvidenceRecord Identity(claim_idに依拠)が異なる限り、古い
    EvidenceへCollapseしない(Fuzzy Equivalence無し)。"""
    norm_doc = _single_member_doc(_ix("jpcrp_cor:BusinessRisksTextBlock", "重要な変更はありません。"))
    span = _span_for(norm_doc)
    candidate_v1 = _candidate(evidence_span=span, extraction_version="EXTRACT_V1")
    candidate_v2 = _candidate(evidence_span=span, extraction_version="EXTRACT_V2")
    claim_v1 = _claim_from_candidate(candidate_v1)
    claim_v2 = _claim_from_candidate(candidate_v2)
    assert claim_v1.claim_id != claim_v2.claim_id  # extraction_versionが異なればclaim_idも異なる

    document = _disclosure_document()
    evidence_v1 = _evidence_for(claim_v1, document)
    evidence_v2 = _evidence_for(claim_v2, document)
    assert evidence_v1.evidence_id != evidence_v2.evidence_id

    result = build_incremental_research_update(
        prior_evidence_records=(evidence_v1,),
        current_evidence_records=(evidence_v1, evidence_v2),
        semantic_claims=(claim_v1, claim_v2),
    )

    assert result.status == EvidenceDeltaStatus.SUCCESS
    assert result.unchanged_evidence_ids == (evidence_v1.evidence_id,)
    assert result.new_evidence_ids == (evidence_v2.evidence_id,)
    assert result.removed_or_missing_evidence_ids == ()


# ============================================================
# §21: Multiple Filing Scenario
# ============================================================


def test_same_company_same_text_different_filings_remain_distinct() -> None:
    """同じ会社・同じclaim_type・同じ文言でも、異なるDisclosureDocument
    (異なるPIT Timestamp)由来であれば別個のEvidenceとして扱う
    (Cross-Document Collapse無し)。"""
    evidence_a, claim_a, _, _, _ = _build_evidence(
        document_id="DOC_A", text="重要な変更はありません。", retrieved_at=datetime(2026, 8, 1, tzinfo=UTC)
    )
    evidence_b, claim_b, _, _, _ = _build_evidence(
        document_id="DOC_B", text="重要な変更はありません。", retrieved_at=datetime(2026, 9, 1, tzinfo=UTC)
    )
    assert evidence_a.evidence_id != evidence_b.evidence_id

    result = build_incremental_research_update(
        prior_evidence_records=(evidence_a,),
        current_evidence_records=(evidence_a, evidence_b),
        semantic_claims=(claim_a, claim_b),
    )

    assert result.status == EvidenceDeltaStatus.SUCCESS
    assert result.unchanged_evidence_ids == (evidence_a.evidence_id,)
    assert result.new_evidence_ids == (evidence_b.evidence_id,)


# ============================================================
# §22: Supersession Safety Tests
# ============================================================


def test_supersession_a_explicit_valid_relation_is_potentially_superseded() -> None:
    old_evidence, old_claim, _, _, _ = _build_evidence(document_id="DOC1", text="旧クレーム。")
    new_evidence, new_claim, _, _, _ = _build_evidence(
        document_id="DOC2",
        text="新クレーム。",
        supersedes_claim_id=old_claim.claim_id,
        retrieved_at=datetime(2026, 9, 1, tzinfo=UTC),
    )

    result = build_incremental_research_update(
        prior_evidence_records=(old_evidence,),
        current_evidence_records=(old_evidence, new_evidence),
        semantic_claims=(old_claim, new_claim),
    )

    assert result.status == EvidenceDeltaStatus.SUCCESS
    assert len(result.potentially_superseded_pairs) == 1
    pair = result.potentially_superseded_pairs[0]
    assert pair.new_evidence_id == new_evidence.evidence_id
    assert pair.old_evidence_id == old_evidence.evidence_id


def test_supersession_b_same_wording_only_is_not_superseded() -> None:
    old_evidence, old_claim, _, _, _ = _build_evidence(document_id="DOC1", text="同じ文言。")
    # supersedes_claim_idを明示的に設定しない -> 文言が同じだけでは推測しない。
    new_evidence, new_claim, _, _, _ = _build_evidence(document_id="DOC2", text="同じ文言。")

    result = build_incremental_research_update(
        prior_evidence_records=(old_evidence,),
        current_evidence_records=(old_evidence, new_evidence),
        semantic_claims=(old_claim, new_claim),
    )

    assert result.status == EvidenceDeltaStatus.SUCCESS
    assert result.potentially_superseded_pairs == ()
    assert new_evidence.evidence_id in result.new_evidence_ids


def test_supersession_c_same_company_only_is_not_superseded() -> None:
    old_evidence, old_claim, _, _, _ = _build_evidence(document_id="DOC1", text="A社の状況。")
    new_evidence, new_claim, _, _, _ = _build_evidence(document_id="DOC2", text="B社の状況。")
    # 両方entity_id="7203"(同一会社、_disclosure_documentの既定)だが
    # supersedes_claim_idは未設定。

    result = build_incremental_research_update(
        prior_evidence_records=(old_evidence,),
        current_evidence_records=(old_evidence, new_evidence),
        semantic_claims=(old_claim, new_claim),
    )

    assert result.potentially_superseded_pairs == ()


def test_supersession_d_opposite_direction_only_is_not_superseded() -> None:
    old_evidence, old_claim, _, _, _ = _build_evidence(
        document_id="DOC1", text="業績は増加する。", direction=ClaimDirection.INCREASE
    )
    new_evidence, new_claim, _, _, _ = _build_evidence(
        document_id="DOC2", text="業績は減少する。", direction=ClaimDirection.DECREASE
    )
    # 方向が反対でもsupersedes_claim_idが無ければSupersessionにしない。

    result = build_incremental_research_update(
        prior_evidence_records=(old_evidence,),
        current_evidence_records=(old_evidence, new_evidence),
        semantic_claims=(old_claim, new_claim),
    )

    assert result.potentially_superseded_pairs == ()


def test_supersession_e_later_available_at_alone_is_not_sufficient() -> None:
    old_evidence, old_claim, _, _, _ = _build_evidence(document_id="DOC1", text="旧クレーム2。")
    new_evidence, new_claim, _, _, _ = _build_evidence(
        document_id="DOC2", text="新クレーム2。", retrieved_at=datetime(2030, 1, 1, tzinfo=UTC)
    )
    assert new_evidence.source.available_at > old_evidence.source.available_at
    # supersedes_claim_idが無いため、PITが新しいだけではSupersessionにしない。

    result = build_incremental_research_update(
        prior_evidence_records=(old_evidence,),
        current_evidence_records=(old_evidence, new_evidence),
        semantic_claims=(old_claim, new_claim),
    )

    assert result.potentially_superseded_pairs == ()


def test_supersession_f_pit_reversal_fails_closed() -> None:
    """明示的supersedes_claim_idがあっても、新Evidenceのavailable_atが
    旧Evidenceより前ならPair化せずpit_failuresへ記録する。"""
    old_evidence, old_claim, _, _, _ = _build_evidence(
        document_id="DOC1", text="旧クレーム3。", retrieved_at=datetime(2026, 9, 1, tzinfo=UTC)
    )
    new_evidence, new_claim, _, _, _ = _build_evidence(
        document_id="DOC2",
        text="新クレーム3。",
        supersedes_claim_id=old_claim.claim_id,
        retrieved_at=datetime(2026, 1, 1, tzinfo=UTC),  # 旧Evidenceより前
    )
    assert new_evidence.source.available_at < old_evidence.source.available_at

    result = build_incremental_research_update(
        prior_evidence_records=(old_evidence,),
        current_evidence_records=(old_evidence, new_evidence),
        semantic_claims=(old_claim, new_claim),
    )

    assert result.status == EvidenceDeltaStatus.SUCCESS
    assert result.potentially_superseded_pairs == ()
    assert len(result.pit_failures) == 1
    assert result.pit_failures[0].new_evidence_id == new_evidence.evidence_id
    assert result.pit_failures[0].old_evidence_id == old_evidence.evidence_id


# ============================================================
# §23: Research Impact Tests
# ============================================================


def test_impact_a_removed_referenced_evidence_requires_review() -> None:
    e1, c1, _, _, _ = _build_evidence(document_id="DOC1", text="Impact A。")
    artifact = _research_artifact("R_A", (e1.evidence_id,))

    result = build_incremental_research_update(
        prior_evidence_records=(e1,), current_evidence_records=(), research_artifacts=(artifact,), semantic_claims=(c1,)
    )

    assert result.affected_research_nodes[0].status == ResearchImpactStatus.REVIEW_REQUIRED


def test_impact_b_superseded_referenced_evidence_requires_review() -> None:
    old_evidence, old_claim, _, _, _ = _build_evidence(document_id="DOC1", text="Impact B old。")
    new_evidence, new_claim, _, _, _ = _build_evidence(
        document_id="DOC2",
        text="Impact B new。",
        supersedes_claim_id=old_claim.claim_id,
        retrieved_at=datetime(2026, 9, 1, tzinfo=UTC),
    )
    artifact = _research_artifact("R_B", (old_evidence.evidence_id,))

    result = build_incremental_research_update(
        prior_evidence_records=(old_evidence,),
        current_evidence_records=(old_evidence, new_evidence),
        research_artifacts=(artifact,),
        semantic_claims=(old_claim, new_claim),
    )

    assert len(result.potentially_superseded_pairs) == 1
    assert result.affected_research_nodes[0].status == ResearchImpactStatus.REVIEW_REQUIRED


def test_impact_c_unchanged_referenced_evidence_is_unaffected() -> None:
    e1, c1, _, _, _ = _build_evidence(document_id="DOC1", text="Impact C。")
    artifact = _research_artifact("R_C", (e1.evidence_id,))

    result = build_incremental_research_update(
        prior_evidence_records=(e1,), current_evidence_records=(e1,), research_artifacts=(artifact,), semantic_claims=(c1,)
    )

    assert result.affected_research_nodes[0].status == ResearchImpactStatus.UNAFFECTED


def test_impact_d_unrelated_new_evidence_does_not_affect_existing_node() -> None:
    e1, c1, _, _, _ = _build_evidence(document_id="DOC1", text="Impact D old。")
    e_new, c_new, _, _, _ = _build_evidence(document_id="DOC2", text="Impact D new。")
    artifact = _research_artifact("R_D", (e1.evidence_id,))  # e_newを参照しない

    result = build_incremental_research_update(
        prior_evidence_records=(e1,),
        current_evidence_records=(e1, e_new),
        research_artifacts=(artifact,),
        semantic_claims=(c1, c_new),
    )

    assert result.affected_research_nodes[0].status == ResearchImpactStatus.UNAFFECTED
    assert e_new.evidence_id in result.unassigned_new_evidence_ids


def test_impact_e_new_unassigned_evidence_enters_queue() -> None:
    e_new, c_new, _, _, _ = _build_evidence(document_id="DOC1", text="Impact E。")

    result = build_incremental_research_update(
        prior_evidence_records=(), current_evidence_records=(e_new,), semantic_claims=(c_new,)
    )

    assert result.unassigned_new_evidence_ids == (e_new.evidence_id,)


def test_impact_f_missing_referenced_evidence_fails_closed() -> None:
    e1, c1, _, _, _ = _build_evidence(document_id="DOC1", text="Impact F。")
    artifact = _research_artifact("R_F", ("EVID_CLAIM_NONEXISTENT",))

    result = build_incremental_research_update(
        prior_evidence_records=(e1,), current_evidence_records=(e1,), research_artifacts=(artifact,), semantic_claims=(c1,)
    )

    assert result.status == EvidenceDeltaStatus.MISSING_REFERENCE
    assert result.affected_research_nodes == ()


def test_impact_g_duplicate_artifact_id_fails_closed() -> None:
    e1, c1, _, _, _ = _build_evidence(document_id="DOC1", text="Impact G。")
    artifact_1 = _research_artifact("R_DUP", (e1.evidence_id,))
    artifact_2 = _research_artifact("R_DUP", (e1.evidence_id,))

    result = build_incremental_research_update(
        prior_evidence_records=(e1,),
        current_evidence_records=(e1,),
        research_artifacts=(artifact_1, artifact_2),
        semantic_claims=(c1,),
    )

    assert result.status == EvidenceDeltaStatus.AMBIGUOUS_REFERENCE


# ============================================================
# 追加: Duplicate IDs / Determinism / Empty Snapshots / Lineage / No-LLM / Immutability
# ============================================================


def test_duplicate_evidence_id_within_one_snapshot_fails_closed() -> None:
    e1, c1, _, _, _ = _build_evidence(document_id="DOC1", text="Dup。")

    result = build_incremental_research_update(
        prior_evidence_records=(e1, e1), current_evidence_records=(e1,), semantic_claims=(c1,)
    )

    assert result.status == EvidenceDeltaStatus.AMBIGUOUS_REFERENCE


def test_output_is_deterministic_under_input_reordering() -> None:
    e1, c1, _, _, _ = _build_evidence(document_id="DOC1", text="Order E1。")
    e2, c2, _, _, _ = _build_evidence(document_id="DOC1", text="Order E2。")
    e3, c3, _, _, _ = _build_evidence(document_id="DOC2", text="Order E3。")

    result_a = build_incremental_research_update(
        prior_evidence_records=(e1, e2), current_evidence_records=(e1, e2, e3), semantic_claims=(c1, c2, c3)
    )
    result_b = build_incremental_research_update(
        prior_evidence_records=(e2, e1), current_evidence_records=(e3, e2, e1), semantic_claims=(c3, c1, c2)
    )

    assert result_a.new_evidence_ids == result_b.new_evidence_ids
    assert result_a.unchanged_evidence_ids == result_b.unchanged_evidence_ids
    assert result_a.removed_or_missing_evidence_ids == result_b.removed_or_missing_evidence_ids


def test_empty_prior_snapshot_all_new() -> None:
    e1, c1, _, _, _ = _build_evidence(document_id="DOC1", text="Empty prior。")

    result = build_incremental_research_update(prior_evidence_records=(), current_evidence_records=(e1,), semantic_claims=(c1,))

    assert result.status == EvidenceDeltaStatus.SUCCESS
    assert result.new_evidence_ids == (e1.evidence_id,)
    assert result.removed_or_missing_evidence_ids == ()
    assert result.unchanged_evidence_ids == ()


def test_empty_current_snapshot_all_removed() -> None:
    e1, c1, _, _, _ = _build_evidence(document_id="DOC1", text="Empty current。")

    result = build_incremental_research_update(prior_evidence_records=(e1,), current_evidence_records=(), semantic_claims=(c1,))

    assert result.status == EvidenceDeltaStatus.SUCCESS
    assert result.removed_or_missing_evidence_ids == (e1.evidence_id,)
    assert result.new_evidence_ids == ()


def test_both_snapshots_empty() -> None:
    result = build_incremental_research_update(prior_evidence_records=(), current_evidence_records=())

    assert result.status == EvidenceDeltaStatus.SUCCESS
    assert result.new_evidence_ids == ()
    assert result.unchanged_evidence_ids == ()
    assert result.removed_or_missing_evidence_ids == ()
    assert result.potentially_superseded_pairs == ()
    assert result.affected_research_nodes == ()


def test_lineage_failure_excludes_from_supersession_and_is_reported() -> None:
    """Lineage Dependencyが供給されているが、NEW Evidenceに対応する
    NormalizedDisclosureDocumentが欠落している場合、lineage_failuresへ
    記録され、そのEvidenceはSupersession Candidateから除外される。"""
    old_evidence, old_claim, _, old_norm_doc, old_document = _build_evidence(document_id="DOC1", text="Lineage old。")
    new_evidence, new_claim, new_candidate, _new_norm_doc, new_document = _build_evidence(
        document_id="DOC2",
        text="Lineage new。",
        supersedes_claim_id=old_claim.claim_id,
        retrieved_at=datetime(2026, 9, 1, tzinfo=UTC),
    )

    result = build_incremental_research_update(
        prior_evidence_records=(old_evidence,),
        current_evidence_records=(old_evidence, new_evidence),
        semantic_claims=(old_claim, new_claim),
        candidates=(new_candidate,),
        normalized_documents=(old_norm_doc,),  # new_evidenceのDOC2用Documentを意図的に欠落させる
        disclosure_documents=(old_document, new_document),
    )

    assert result.status == EvidenceDeltaStatus.SUCCESS
    assert len(result.lineage_failures) == 1
    assert result.lineage_failures[0].evidence_id == new_evidence.evidence_id
    assert result.potentially_superseded_pairs == ()  # Lineage未確認のためPair化しない


def test_no_lineage_dependencies_skips_lineage_check_without_failure() -> None:
    e1, c1, _, _, _ = _build_evidence(document_id="DOC1", text="No lineage deps。")

    result = build_incremental_research_update(prior_evidence_records=(), current_evidence_records=(e1,), semantic_claims=(c1,))

    assert result.status == EvidenceDeltaStatus.SUCCESS
    assert result.lineage_failures == ()


def test_incremental_update_module_has_no_model_dependency() -> None:
    source = Path(incremental_update_module.__file__).read_text(encoding="utf-8")
    for forbidden in ("CandidateExtractionModel", "FaithfulnessVerifier", ".extract(", "import openai", "import anthropic"):
        assert forbidden not in source


def test_incremental_update_module_has_no_decision_logic() -> None:
    source = Path(incremental_update_module.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    identifiers: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            identifiers.add(node.id)
        elif isinstance(node, ast.Attribute):
            identifiers.add(node.attr)
        elif isinstance(node, ast.arg):
            identifiers.add(node.arg)
        elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            identifiers.add(node.name)
        elif isinstance(node, ast.alias):
            identifiers.add(node.name)
            if node.asname:
                identifiers.add(node.asname)
    joined = " ".join(identifiers)
    forbidden_terms = ("Bull", "Bear", "BUY", "SELL", "expected_return", "confidence", "valuation", "PositionSiz")
    for forbidden in forbidden_terms:
        assert forbidden not in joined


def test_incremental_update_module_never_constructs_research_artifact_or_narrative_case() -> None:
    # D0105 §17: Read-Onlyであり、ResearchArtifact/NarrativeCaseを一切
    # 構築・Mutateしない(Importのみ、インスタンス化は無い)。
    source = Path(incremental_update_module.__file__).read_text(encoding="utf-8")
    assert "ResearchArtifact(" not in source
    assert "NarrativeCase(" not in source


def test_research_artifact_input_remains_unmutated() -> None:
    e1, c1, _, _, _ = _build_evidence(document_id="DOC1", text="Immutable。")
    artifact = _research_artifact("R_IMMUT", (e1.evidence_id,))
    snapshot = ResearchArtifact(**{f.name: getattr(artifact, f.name) for f in artifact.__dataclass_fields__.values()})

    build_incremental_research_update(
        prior_evidence_records=(e1,), current_evidence_records=(e1,), research_artifacts=(artifact,), semantic_claims=(c1,)
    )

    assert artifact == snapshot


def test_build_incremental_research_update_returns_immutable_result_type() -> None:
    result = build_incremental_research_update(prior_evidence_records=(), current_evidence_records=())
    assert isinstance(result, IncrementalResearchUpdateResult)


# ============================================================
# Code Review Finding(D0105)Closure
# ============================================================


def test_duplicate_source_id_across_distinct_evidence_ids_fails_closed() -> None:
    """同一evidence.source.source_id(claim_id)が2つの異なるevidence_idに
    対応する場合(Authoritative Join Keyの一意性違反、通常のevidence_id
    重複Checkでは検知できないClass)、Silent First-Matchせず
    AMBIGUOUS_REFERENCEでFail Closedする。入力順序を反転しても同じ
    Statusになること(Reordering非依存)も確認する。"""
    e1, c1, _, _, old_document = _build_evidence(document_id="DOC1", text="Dup source_id old。")
    duplicate_evidence = type(e1)(
        evidence_id="EVID_CLAIM_DUPLICATE",
        evidence_type=e1.evidence_type,
        layer=e1.layer,
        capability=e1.capability,
        content=e1.content,
        source=e1.source,  # 同一source(=同一source_id=claim_id)だが別evidence_id
    )
    e_new, c_new, _, _, _ = _build_evidence(document_id="DOC2", text="Dup source_id new。", supersedes_claim_id=c1.claim_id)

    result_a = build_incremental_research_update(
        prior_evidence_records=(e1, duplicate_evidence),
        current_evidence_records=(e1, duplicate_evidence, e_new),
        semantic_claims=(c1, c_new),
    )
    result_b = build_incremental_research_update(
        prior_evidence_records=(duplicate_evidence, e1),
        current_evidence_records=(duplicate_evidence, e1, e_new),
        semantic_claims=(c1, c_new),
    )

    assert result_a.status == EvidenceDeltaStatus.AMBIGUOUS_REFERENCE
    assert result_b.status == EvidenceDeltaStatus.AMBIGUOUS_REFERENCE
    assert result_a.potentially_superseded_pairs == ()
    assert result_b.potentially_superseded_pairs == ()


def test_non_evidence_record_element_raises_schema_error_not_attribute_error() -> None:
    """`prior_evidence_records`/`current_evidence_records`の各要素が
    `EvidenceRecord`でない場合、素の`AttributeError`を漏らさず
    `IncrementalResearchUpdateSchemaError`で明示的に拒否する(Caller
    Programming ErrorとDomain Outcomeを区別する既存契約、D0103/D0104と
    同じ方針)。"""
    with pytest.raises(IncrementalResearchUpdateSchemaError):
        build_incremental_research_update(
            prior_evidence_records=({"not": "an EvidenceRecord"},),  # type: ignore[arg-type]
            current_evidence_records=(),
        )
