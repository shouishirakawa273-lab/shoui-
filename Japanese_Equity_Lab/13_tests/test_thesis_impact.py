"""`lib.evidence.thesis_impact`(D0106)のRegression Test。

`assess_thesis_impact()`が以下を機械的に強制することを検証する:

1. Deterministic GateがSemantic Interpretation(Model呼び出し)より常に
   先行し、いずれかのGateが失敗すればModelは一切呼び出されないこと。
2. `EvidenceRelation`(既存Enum、SUPPORTS/CONTRADICTS/ALTERNATIVE_
   EXPLANATION/NEUTRAL/UNKNOWN)をそのまま再利用し、CONTRADICTSと
   ALTERNATIVE_EXPLANATIONを混同しないこと。
3. `REMOVED_OR_MISSING`が自動的にCONTRADICTSを意味しないこと。
4. Bull/Base/Bearが独立に評価され、1つのGlobal Relationを強制しない
   こと(Scenario Isolation)。
5. Unassigned NEW Evidenceが自動的にどのScenarioへもAttachされない
   こと。
6. `ResearchArtifact`/`NarrativeCase`を一切Mutateしないこと。
7. Model出力がSchema-Constrainedであり、未知のKey(Thesis書き換え・
   BUY/SELL密輸等)・不正なEnum値をいずれもReject(Whole-Response-
   Fatal)すること。
8. Model呼び出しが無い場合は`relation=UNKNOWN`で推測しないこと。

Fixture方式は`test_incremental_research_update.py`と同じ(Synthetic
EDINET-shaped ZIPを構築し、実際のD0101.1/D0102.x/D0103経路でReal
EvidenceRecordを得る)。
"""

from __future__ import annotations

import ast
import io
import zipfile
from dataclasses import dataclass, field
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
from lib.evidence import thesis_impact as thesis_impact_module
from lib.evidence.incremental_update import IncrementalResearchUpdateResult, build_incremental_research_update
from lib.evidence.model import AiDerivedProvenance, AvailabilityBasis, EvidenceRecord, EvidenceRelation
from lib.evidence.research_artifact import ConfidenceLevel, NarrativeCase, ResearchArtifact, ResearchConclusion
from lib.evidence.thesis_impact import (
    EvidenceChangeKind,
    ThesisAssessmentStatus,
    ThesisImpactResult,
    ThesisImpactSchemaError,
    ThesisRelationModelInput,
    ThesisScenario,
    assess_thesis_impact,
)
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
    candidate: SemanticClaimCandidate, *, faithfulness_outcome: FaithfulnessOutcome = FaithfulnessOutcome.ACCEPT
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
    )


def _disclosure_document(
    *,
    internal_document_id: str = "DOC1",
    entity_id: str | None = "7203",
    provider_available_at: datetime | None = None,
    provider_available_at_basis: AvailabilityBasis = AvailabilityBasis.UNKNOWN,
    retrieved_at: datetime = datetime(2026, 8, 17, 15, 6, tzinfo=UTC),
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
    )


def _evidence_for(claim: SemanticClaim, document: DisclosureDocument) -> EvidenceRecord:
    result = integrate_accepted_semantic_claim(
        claim=claim, document=document, source_authority_class=SourceAuthorityClass.PRIMARY_OFFICIAL
    )
    assert result.evidence is not None
    return result.evidence


def _build_evidence(
    *,
    document_id: str = "DOC1",
    text: str = "重要な変更はありません。",
    occurrence: int = 0,
    extraction_version: str = "EXTRACT_V1",
    direction: ClaimDirection = ClaimDirection.UNSPECIFIED,
    faithfulness_outcome: FaithfulnessOutcome = FaithfulnessOutcome.ACCEPT,
    retrieved_at: datetime = datetime(2026, 8, 17, 15, 6, tzinfo=UTC),
    body_extra: str = "",
) -> tuple[EvidenceRecord | None, SemanticClaim, SemanticClaimCandidate, NormalizedDisclosureDocument, DisclosureDocument]:
    body = _ix("jpcrp_cor:BusinessRisksTextBlock", text) + body_extra
    norm_doc = _single_member_doc(body, document_id=document_id)
    span = _span_for(norm_doc, occurrence=occurrence)
    candidate = _candidate(
        evidence_span=span, normalized_claim_text=text, direction=direction, extraction_version=extraction_version
    )
    claim = _claim_from_candidate(candidate, faithfulness_outcome=faithfulness_outcome)
    document = _disclosure_document(internal_document_id=document_id, retrieved_at=retrieved_at)
    evidence = None
    if faithfulness_outcome is FaithfulnessOutcome.ACCEPT:
        evidence = _evidence_for(claim, document)
    return evidence, claim, candidate, norm_doc, document


def _research_artifact(
    artifact_id: str,
    *,
    included_evidence_ids: tuple[str, ...],
    bull_evidence_ids: tuple[str, ...] = (),
    base_evidence_ids: tuple[str, ...] = (),
    bear_evidence_ids: tuple[str, ...] = (),
) -> ResearchArtifact:
    conclusion = ResearchConclusion.SUPPORTED if included_evidence_ids else ResearchConclusion.INSUFFICIENT_EVIDENCE
    confidence = ConfidenceLevel.MEDIUM if included_evidence_ids else ConfidenceLevel.INSUFFICIENT
    return ResearchArtifact(
        artifact_id=artifact_id,
        entity_code="7203",
        as_of=datetime(2026, 8, 20, tzinfo=UTC),
        research_question_id="RQ_TEST_0001",
        evidence_packet_id=f"PKT_{artifact_id}",
        bull_case=NarrativeCase(
            summary="原材料高による一時的な悪化であり中期的には回復する", supporting_evidence_ids=bull_evidence_ids
        ),
        base_case=NarrativeCase(summary="マージン悪化は原材料インフレが原因である", supporting_evidence_ids=base_evidence_ids),
        bear_case=NarrativeCase(summary="構造的な価格競争力の劣化である", supporting_evidence_ids=bear_evidence_ids),
        data_confidence=confidence,
        evidence_confidence=confidence,
        research_confidence=confidence,
        conclusion=conclusion,
        conclusion_rationale="test fixture",
        included_evidence_ids=included_evidence_ids,
    )


@dataclass
class FakeThesisRelationModel:
    """`ThesisRelationModel` Protocolを満たすIn-Process Test Double。
    `response_fn`は受け取った`model_input`を基に生Output(通常dict)を
    返す——Closure越しにScenario別の異なる応答を返すTestで使う。"""

    response_fn: object = None
    fixed_response: object = None
    calls: list[ThesisRelationModelInput] = field(default_factory=list)

    def classify(self, *, model_input: ThesisRelationModelInput) -> object:
        self.calls.append(model_input)
        if self.response_fn is not None:
            return self.response_fn(model_input)  # type: ignore[misc]
        return self.fixed_response

    @property
    def call_count(self) -> int:
        return len(self.calls)


def _relation_response(
    relation: EvidenceRelation, *, reason: str = "test reason", uncertainty: str | None = None
) -> dict[str, object]:
    return {"relation": relation.value, "reason": reason, "uncertainty": uncertainty}


_NOW = datetime(2026, 9, 1, tzinfo=UTC)


def _assert_assessed(result: ThesisImpactResult) -> None:
    assert result.status == ThesisAssessmentStatus.ASSESSED
    assert result.assessment is not None


# ============================================================
# §21 A-E: Relation Classification Pass-Through
# ============================================================


def test_a_new_evidence_contradicts_base_requires_review() -> None:
    evidence, claim, candidate, norm_doc, document = _build_evidence(
        document_id="DOC1", text="販促費による一時的な値引きが主因である。"
    )
    assert evidence is not None
    update = build_incremental_research_update(
        prior_evidence_records=(), current_evidence_records=(evidence,), semantic_claims=(claim,)
    )
    artifact = _research_artifact("R1", included_evidence_ids=(), base_evidence_ids=())
    model = FakeThesisRelationModel(fixed_response=_relation_response(EvidenceRelation.CONTRADICTS))

    result = assess_thesis_impact(
        research_artifact=artifact,
        scenario=ThesisScenario.BASE,
        evidence_id=evidence.evidence_id,
        incremental_update=update,
        decision_at=_NOW,
        assessed_at=_NOW,
        evidence_records=(evidence,),
        semantic_claims=(claim,),
        candidates=(candidate,),
        normalized_documents=(norm_doc,),
        disclosure_documents=(document,),
        model=model,
        model_provider="test",
        model_name="test-model",
        prompt_hash="HASH1",
    )

    _assert_assessed(result)
    assert result.assessment.relation == EvidenceRelation.CONTRADICTS
    assert result.assessment.requires_review is True
    assert model.call_count == 1


def test_b_new_evidence_supports_base() -> None:
    evidence, claim, candidate, norm_doc, document = _build_evidence(document_id="DOC1", text="原材料費の上昇が主因である。")
    assert evidence is not None
    update = build_incremental_research_update(
        prior_evidence_records=(), current_evidence_records=(evidence,), semantic_claims=(claim,)
    )
    artifact = _research_artifact("R1", included_evidence_ids=())
    model = FakeThesisRelationModel(fixed_response=_relation_response(EvidenceRelation.SUPPORTS))

    result = assess_thesis_impact(
        research_artifact=artifact,
        scenario=ThesisScenario.BASE,
        evidence_id=evidence.evidence_id,
        incremental_update=update,
        decision_at=_NOW,
        assessed_at=_NOW,
        evidence_records=(evidence,),
        semantic_claims=(claim,),
        candidates=(candidate,),
        normalized_documents=(norm_doc,),
        disclosure_documents=(document,),
        model=model,
        model_provider="test",
        model_name="test-model",
        prompt_hash="HASH1",
    )

    _assert_assessed(result)
    assert result.assessment.relation == EvidenceRelation.SUPPORTS
    assert result.assessment.requires_review is False


def test_c_alternative_explanation_remains_distinct_from_contradicts() -> None:
    """D0106 §4/§29-5: ALTERNATIVE_EXPLANATIONはCONTRADICTSと混同しない。
    例: 「マージン悪化は原材料インフレが原因」というBase Hypothesisに対し、
    「経営陣は販促費の値引きが主因と説明」というEvidenceは、直接的な
    論理矛盾ではなく競合する説明である。"""
    evidence, claim, candidate, norm_doc, document = _build_evidence(
        document_id="DOC1", text="経営陣は販促費の値引きが主因と説明している。"
    )
    assert evidence is not None
    update = build_incremental_research_update(
        prior_evidence_records=(), current_evidence_records=(evidence,), semantic_claims=(claim,)
    )
    artifact = _research_artifact("R1", included_evidence_ids=())
    model = FakeThesisRelationModel(fixed_response=_relation_response(EvidenceRelation.ALTERNATIVE_EXPLANATION))

    result = assess_thesis_impact(
        research_artifact=artifact,
        scenario=ThesisScenario.BASE,
        evidence_id=evidence.evidence_id,
        incremental_update=update,
        decision_at=_NOW,
        assessed_at=_NOW,
        evidence_records=(evidence,),
        semantic_claims=(claim,),
        candidates=(candidate,),
        normalized_documents=(norm_doc,),
        disclosure_documents=(document,),
        model=model,
        model_provider="test",
        model_name="test-model",
        prompt_hash="HASH1",
    )

    _assert_assessed(result)
    assert result.assessment.relation == EvidenceRelation.ALTERNATIVE_EXPLANATION
    assert result.assessment.relation != EvidenceRelation.CONTRADICTS
    assert result.assessment.requires_review is True


def test_d_unrelated_evidence_is_neutral() -> None:
    evidence, claim, candidate, norm_doc, document = _build_evidence(document_id="DOC1", text="本社移転を実施した。")
    assert evidence is not None
    update = build_incremental_research_update(
        prior_evidence_records=(), current_evidence_records=(evidence,), semantic_claims=(claim,)
    )
    artifact = _research_artifact("R1", included_evidence_ids=())
    model = FakeThesisRelationModel(fixed_response=_relation_response(EvidenceRelation.NEUTRAL))

    result = assess_thesis_impact(
        research_artifact=artifact,
        scenario=ThesisScenario.BASE,
        evidence_id=evidence.evidence_id,
        incremental_update=update,
        decision_at=_NOW,
        assessed_at=_NOW,
        evidence_records=(evidence,),
        semantic_claims=(claim,),
        candidates=(candidate,),
        normalized_documents=(norm_doc,),
        disclosure_documents=(document,),
        model=model,
        model_provider="test",
        model_name="test-model",
        prompt_hash="HASH1",
    )

    _assert_assessed(result)
    assert result.assessment.relation == EvidenceRelation.NEUTRAL
    assert result.assessment.requires_review is False


def test_e_semantic_relationship_unclear_is_unknown() -> None:
    evidence, claim, candidate, norm_doc, document = _build_evidence(document_id="DOC1", text="状況は複雑である。")
    assert evidence is not None
    update = build_incremental_research_update(
        prior_evidence_records=(), current_evidence_records=(evidence,), semantic_claims=(claim,)
    )
    artifact = _research_artifact("R1", included_evidence_ids=())
    model = FakeThesisRelationModel(fixed_response=_relation_response(EvidenceRelation.UNKNOWN))

    result = assess_thesis_impact(
        research_artifact=artifact,
        scenario=ThesisScenario.BASE,
        evidence_id=evidence.evidence_id,
        incremental_update=update,
        decision_at=_NOW,
        assessed_at=_NOW,
        evidence_records=(evidence,),
        semantic_claims=(claim,),
        candidates=(candidate,),
        normalized_documents=(norm_doc,),
        disclosure_documents=(document,),
        model=model,
        model_provider="test",
        model_name="test-model",
        prompt_hash="HASH1",
    )

    _assert_assessed(result)
    assert result.assessment.relation == EvidenceRelation.UNKNOWN
    assert result.assessment.requires_review is True


# ============================================================
# §21 F-I: Deterministic Gate Blocks Model Call
# ============================================================


def test_f_removed_evidence_requires_review_not_contradicts() -> None:
    """REMOVED_OR_MISSINGは自動的にCONTRADICTSを意味しない(D0106 §12)。
    Modelは一切呼び出されない。"""
    old_evidence, old_claim, _, _, _ = _build_evidence(document_id="DOC1", text="旧根拠。")
    assert old_evidence is not None
    update = build_incremental_research_update(
        prior_evidence_records=(old_evidence,), current_evidence_records=(), semantic_claims=(old_claim,)
    )
    artifact = _research_artifact(
        "R1", included_evidence_ids=(old_evidence.evidence_id,), base_evidence_ids=(old_evidence.evidence_id,)
    )
    model = FakeThesisRelationModel(fixed_response=_relation_response(EvidenceRelation.CONTRADICTS))

    result = assess_thesis_impact(
        research_artifact=artifact,
        scenario=ThesisScenario.BASE,
        evidence_id=old_evidence.evidence_id,
        incremental_update=update,
        decision_at=_NOW,
        assessed_at=_NOW,
        model=model,
        model_provider="test",
        model_name="test-model",
        prompt_hash="HASH1",
    )

    _assert_assessed(result)
    assert result.assessment.relation == EvidenceRelation.UNKNOWN
    assert result.assessment.relation != EvidenceRelation.CONTRADICTS
    assert result.assessment.requires_review is True
    assert result.assessment.reason.startswith("EVIDENCE_MISSING")
    assert model.call_count == 0


def test_g_lineage_failure_prevents_model_call() -> None:
    evidence, claim, candidate, _norm_doc, document = _build_evidence(document_id="DOC1", text="Lineage不整合テスト。")
    assert evidence is not None
    update = build_incremental_research_update(
        prior_evidence_records=(), current_evidence_records=(evidence,), semantic_claims=(claim,)
    )
    artifact = _research_artifact("R1", included_evidence_ids=())
    model = FakeThesisRelationModel(fixed_response=_relation_response(EvidenceRelation.CONTRADICTS))

    result = assess_thesis_impact(
        research_artifact=artifact,
        scenario=ThesisScenario.BASE,
        evidence_id=evidence.evidence_id,
        incremental_update=update,
        decision_at=_NOW,
        assessed_at=_NOW,
        evidence_records=(evidence,),
        semantic_claims=(claim,),
        candidates=(candidate,),
        normalized_documents=(),  # 意図的に欠落させる -> Lineage失敗
        disclosure_documents=(document,),
        model=model,
        model_provider="test",
        model_name="test-model",
        prompt_hash="HASH1",
    )

    assert result.status == ThesisAssessmentStatus.LINEAGE_FAILURE
    assert result.assessment is None
    assert model.call_count == 0


def test_h_pit_invalid_evidence_prevents_model_call() -> None:
    evidence, claim, _, _, _ = _build_evidence(
        document_id="DOC1", text="将来のPIT境界テスト。", retrieved_at=datetime(2030, 1, 1, tzinfo=UTC)
    )
    assert evidence is not None
    update = build_incremental_research_update(
        prior_evidence_records=(), current_evidence_records=(evidence,), semantic_claims=(claim,)
    )
    artifact = _research_artifact("R1", included_evidence_ids=())
    model = FakeThesisRelationModel(fixed_response=_relation_response(EvidenceRelation.CONTRADICTS))

    result = assess_thesis_impact(
        research_artifact=artifact,
        scenario=ThesisScenario.BASE,
        evidence_id=evidence.evidence_id,
        incremental_update=update,
        decision_at=datetime(2026, 1, 1, tzinfo=UTC),  # evidence.available_atより前
        assessed_at=_NOW,
        evidence_records=(evidence,),
        semantic_claims=(claim,),
        model=model,
        model_provider="test",
        model_name="test-model",
        prompt_hash="HASH1",
    )

    assert result.status == ThesisAssessmentStatus.PIT_MISMATCH
    assert result.assessment is None
    assert model.call_count == 0


def test_i_non_accept_evidence_prevents_model_call() -> None:
    """非ACCEPT(REVIEW_REQUIRED)のClaimはEvidenceRecordへ昇格しない
    (D0103 ACCEPT-only Gate)ため、ここではEvidenceRecordを直接構築して
    Claimだけ非ACCEPTにし、Lineage Resolverが拒否することを確認する。"""
    _no_evidence, accept_claim, candidate, norm_doc, document = _build_evidence(document_id="DOC1", text="非ACCEPTテスト。")
    review_required_claim = _claim_from_candidate(candidate, faithfulness_outcome=FaithfulnessOutcome.REVIEW_REQUIRED)
    evidence = _evidence_for(accept_claim, document)
    update = build_incremental_research_update(
        prior_evidence_records=(), current_evidence_records=(evidence,), semantic_claims=(review_required_claim,)
    )
    artifact = _research_artifact("R1", included_evidence_ids=())
    model = FakeThesisRelationModel(fixed_response=_relation_response(EvidenceRelation.CONTRADICTS))

    result = assess_thesis_impact(
        research_artifact=artifact,
        scenario=ThesisScenario.BASE,
        evidence_id=evidence.evidence_id,
        incremental_update=update,
        decision_at=_NOW,
        assessed_at=_NOW,
        evidence_records=(evidence,),
        semantic_claims=(review_required_claim,),
        candidates=(candidate,),
        normalized_documents=(norm_doc,),
        disclosure_documents=(document,),
        model=model,
        model_provider="test",
        model_name="test-model",
        prompt_hash="HASH1",
    )

    assert result.status == ThesisAssessmentStatus.LINEAGE_FAILURE
    assert model.call_count == 0


# ============================================================
# §21 J: Scenario Isolation
# ============================================================


def test_j_same_evidence_assessed_independently_against_bull_base_bear() -> None:
    evidence, claim, candidate, norm_doc, document = _build_evidence(document_id="DOC1", text="Scenario別評価テスト。")
    assert evidence is not None
    update = build_incremental_research_update(
        prior_evidence_records=(), current_evidence_records=(evidence,), semantic_claims=(claim,)
    )
    artifact = _research_artifact("R1", included_evidence_ids=())

    def _by_scenario(model_input: ThesisRelationModelInput) -> dict[str, object]:
        mapping = {
            ThesisScenario.BULL: EvidenceRelation.CONTRADICTS,
            ThesisScenario.BASE: EvidenceRelation.SUPPORTS,
            ThesisScenario.BEAR: EvidenceRelation.NEUTRAL,
        }
        return _relation_response(mapping[model_input.scenario])

    results = {}
    for scenario in (ThesisScenario.BULL, ThesisScenario.BASE, ThesisScenario.BEAR):
        model = FakeThesisRelationModel(response_fn=_by_scenario)
        results[scenario] = assess_thesis_impact(
            research_artifact=artifact,
            scenario=scenario,
            evidence_id=evidence.evidence_id,
            incremental_update=update,
            decision_at=_NOW,
            assessed_at=_NOW,
            evidence_records=(evidence,),
            semantic_claims=(claim,),
            candidates=(candidate,),
            normalized_documents=(norm_doc,),
            disclosure_documents=(document,),
            model=model,
            model_provider="test",
            model_name="test-model",
            prompt_hash="HASH1",
        )

    assert results[ThesisScenario.BULL].assessment.relation == EvidenceRelation.CONTRADICTS
    assert results[ThesisScenario.BASE].assessment.relation == EvidenceRelation.SUPPORTS
    assert results[ThesisScenario.BEAR].assessment.relation == EvidenceRelation.NEUTRAL


# ============================================================
# §21 K: Unassigned NEW Evidence Not Auto-Attached
# ============================================================


def test_k_unassigned_new_evidence_remains_in_d0105_queue_not_auto_attached() -> None:
    evidence, claim, _, _, _ = _build_evidence(document_id="DOC1", text="未割当NEW Evidence。")
    assert evidence is not None
    update = build_incremental_research_update(
        prior_evidence_records=(), current_evidence_records=(evidence,), semantic_claims=(claim,)
    )

    assert evidence.evidence_id in update.unassigned_new_evidence_ids
    # D0106はこのQueueを自動的にどのArtifactへも結び付けない
    # (Source Levelでも自動Routing Logicが存在しないことを別Testで確認する)。


def test_thesis_impact_module_never_auto_iterates_unassigned_queue() -> None:
    source = Path(thesis_impact_module.__file__).read_text(encoding="utf-8")
    assert "unassigned_new_evidence_ids" not in source


# ============================================================
# §21 L: ResearchArtifact Immutability
# ============================================================


def test_l_research_artifact_remains_unchanged() -> None:
    evidence, claim, candidate, norm_doc, document = _build_evidence(document_id="DOC1", text="Immutable Artifactテスト。")
    assert evidence is not None
    update = build_incremental_research_update(
        prior_evidence_records=(), current_evidence_records=(evidence,), semantic_claims=(claim,)
    )
    artifact = _research_artifact("R1", included_evidence_ids=())
    snapshot = ResearchArtifact(**{f.name: getattr(artifact, f.name) for f in artifact.__dataclass_fields__.values()})
    model = FakeThesisRelationModel(fixed_response=_relation_response(EvidenceRelation.CONTRADICTS))

    assess_thesis_impact(
        research_artifact=artifact,
        scenario=ThesisScenario.BASE,
        evidence_id=evidence.evidence_id,
        incremental_update=update,
        decision_at=_NOW,
        assessed_at=_NOW,
        evidence_records=(evidence,),
        semantic_claims=(claim,),
        candidates=(candidate,),
        normalized_documents=(norm_doc,),
        disclosure_documents=(document,),
        model=model,
        model_provider="test",
        model_name="test-model",
        prompt_hash="HASH1",
    )

    assert artifact == snapshot


# ============================================================
# No Model Configured
# ============================================================


def test_no_model_configured_returns_unknown_without_guessing() -> None:
    evidence, claim, candidate, norm_doc, document = _build_evidence(document_id="DOC1", text="Model未設定テスト。")
    assert evidence is not None
    update = build_incremental_research_update(
        prior_evidence_records=(), current_evidence_records=(evidence,), semantic_claims=(claim,)
    )
    artifact = _research_artifact("R1", included_evidence_ids=())

    result = assess_thesis_impact(
        research_artifact=artifact,
        scenario=ThesisScenario.BASE,
        evidence_id=evidence.evidence_id,
        incremental_update=update,
        decision_at=_NOW,
        assessed_at=_NOW,
        evidence_records=(evidence,),
        semantic_claims=(claim,),
        candidates=(candidate,),
        normalized_documents=(norm_doc,),
        disclosure_documents=(document,),
        model=None,
    )

    _assert_assessed(result)
    assert result.assessment.relation == EvidenceRelation.UNKNOWN
    assert result.assessment.requires_review is True
    assert result.assessment.assessment_provenance is None


# ============================================================
# §23: Model Contract Tests
# ============================================================


def test_model_contract_invalid_relation_enum_rejected() -> None:
    evidence, claim, candidate, norm_doc, document = _build_evidence(document_id="DOC1", text="無効なRelationテスト。")
    assert evidence is not None
    update = build_incremental_research_update(
        prior_evidence_records=(), current_evidence_records=(evidence,), semantic_claims=(claim,)
    )
    artifact = _research_artifact("R1", included_evidence_ids=())
    model = FakeThesisRelationModel(fixed_response={"relation": "BULLISH", "reason": "x", "uncertainty": None})

    result = assess_thesis_impact(
        research_artifact=artifact,
        scenario=ThesisScenario.BASE,
        evidence_id=evidence.evidence_id,
        incremental_update=update,
        decision_at=_NOW,
        assessed_at=_NOW,
        evidence_records=(evidence,),
        semantic_claims=(claim,),
        candidates=(candidate,),
        normalized_documents=(norm_doc,),
        disclosure_documents=(document,),
        model=model,
        model_provider="test",
        model_name="test-model",
        prompt_hash="HASH1",
    )

    assert result.status == ThesisAssessmentStatus.MODEL_CONTRACT_VIOLATION
    assert result.assessment is None


def test_model_contract_prose_only_output_rejected() -> None:
    evidence, claim, candidate, norm_doc, document = _build_evidence(document_id="DOC1", text="Prose-onlyテスト。")
    assert evidence is not None
    update = build_incremental_research_update(
        prior_evidence_records=(), current_evidence_records=(evidence,), semantic_claims=(claim,)
    )
    artifact = _research_artifact("R1", included_evidence_ids=())
    model = FakeThesisRelationModel(fixed_response="This evidence contradicts the thesis.")

    result = assess_thesis_impact(
        research_artifact=artifact,
        scenario=ThesisScenario.BASE,
        evidence_id=evidence.evidence_id,
        incremental_update=update,
        decision_at=_NOW,
        assessed_at=_NOW,
        evidence_records=(evidence,),
        semantic_claims=(claim,),
        candidates=(candidate,),
        normalized_documents=(norm_doc,),
        disclosure_documents=(document,),
        model=model,
        model_provider="test",
        model_name="test-model",
        prompt_hash="HASH1",
    )

    assert result.status == ThesisAssessmentStatus.MODEL_CONTRACT_VIOLATION


def test_model_contract_missing_reason_rejected() -> None:
    evidence, claim, candidate, norm_doc, document = _build_evidence(document_id="DOC1", text="Reason欠落テスト。")
    assert evidence is not None
    update = build_incremental_research_update(
        prior_evidence_records=(), current_evidence_records=(evidence,), semantic_claims=(claim,)
    )
    artifact = _research_artifact("R1", included_evidence_ids=())
    model = FakeThesisRelationModel(fixed_response={"relation": "SUPPORTS", "uncertainty": None})

    result = assess_thesis_impact(
        research_artifact=artifact,
        scenario=ThesisScenario.BASE,
        evidence_id=evidence.evidence_id,
        incremental_update=update,
        decision_at=_NOW,
        assessed_at=_NOW,
        evidence_records=(evidence,),
        semantic_claims=(claim,),
        candidates=(candidate,),
        normalized_documents=(norm_doc,),
        disclosure_documents=(document,),
        model=model,
        model_provider="test",
        model_name="test-model",
        prompt_hash="HASH1",
    )

    assert result.status == ThesisAssessmentStatus.MODEL_CONTRACT_VIOLATION


def test_model_contract_thesis_rewrite_attempt_rejected() -> None:
    """ModelがHypothesis書き換え・BUY/SELL等をKeyとして密輸しようとした
    場合、Response全体をRejectする(Candidate単位のSkipではない、D0106
    §9/§23)。"""
    evidence, claim, candidate, norm_doc, document = _build_evidence(document_id="DOC1", text="Thesis書き換え試行テスト。")
    assert evidence is not None
    update = build_incremental_research_update(
        prior_evidence_records=(), current_evidence_records=(evidence,), semantic_claims=(claim,)
    )
    artifact = _research_artifact("R1", included_evidence_ids=())
    model = FakeThesisRelationModel(
        fixed_response={
            "relation": "SUPPORTS",
            "reason": "x",
            "uncertainty": None,
            "rewritten_base_case": "新しいThesis文",
        }
    )

    result = assess_thesis_impact(
        research_artifact=artifact,
        scenario=ThesisScenario.BASE,
        evidence_id=evidence.evidence_id,
        incremental_update=update,
        decision_at=_NOW,
        assessed_at=_NOW,
        evidence_records=(evidence,),
        semantic_claims=(claim,),
        candidates=(candidate,),
        normalized_documents=(norm_doc,),
        disclosure_documents=(document,),
        model=model,
        model_provider="test",
        model_name="test-model",
        prompt_hash="HASH1",
    )

    assert result.status == ThesisAssessmentStatus.MODEL_CONTRACT_VIOLATION
    assert artifact.base_case.summary == "マージン悪化は原材料インフレが原因である"


def test_model_contract_buy_sell_key_rejected() -> None:
    evidence, claim, candidate, norm_doc, document = _build_evidence(document_id="DOC1", text="BUY/SELL密輸テスト。")
    assert evidence is not None
    update = build_incremental_research_update(
        prior_evidence_records=(), current_evidence_records=(evidence,), semantic_claims=(claim,)
    )
    artifact = _research_artifact("R1", included_evidence_ids=())
    model = FakeThesisRelationModel(fixed_response={"relation": "SUPPORTS", "reason": "x", "uncertainty": None, "action": "BUY"})

    result = assess_thesis_impact(
        research_artifact=artifact,
        scenario=ThesisScenario.BASE,
        evidence_id=evidence.evidence_id,
        incremental_update=update,
        decision_at=_NOW,
        assessed_at=_NOW,
        evidence_records=(evidence,),
        semantic_claims=(claim,),
        candidates=(candidate,),
        normalized_documents=(norm_doc,),
        disclosure_documents=(document,),
        model=model,
        model_provider="test",
        model_name="test-model",
        prompt_hash="HASH1",
    )

    assert result.status == ThesisAssessmentStatus.MODEL_CONTRACT_VIOLATION


# ============================================================
# Deterministic Reference / Materiality / Identity Gates
# ============================================================


def test_missing_evidence_reference_fails_closed() -> None:
    update = build_incremental_research_update(prior_evidence_records=(), current_evidence_records=())
    artifact = _research_artifact("R1", included_evidence_ids=())

    result = assess_thesis_impact(
        research_artifact=artifact,
        scenario=ThesisScenario.BASE,
        evidence_id="EVID_CLAIM_NONEXISTENT",
        incremental_update=update,
        decision_at=_NOW,
        assessed_at=_NOW,
    )

    assert result.status == ThesisAssessmentStatus.MISSING_REFERENCE


def test_unchanged_evidence_is_unsupported_input() -> None:
    evidence, claim, _, _, _ = _build_evidence(document_id="DOC1", text="UNCHANGEDテスト。")
    assert evidence is not None
    update = build_incremental_research_update(
        prior_evidence_records=(evidence,), current_evidence_records=(evidence,), semantic_claims=(claim,)
    )
    artifact = _research_artifact("R1", included_evidence_ids=(evidence.evidence_id,))

    result = assess_thesis_impact(
        research_artifact=artifact,
        scenario=ThesisScenario.BASE,
        evidence_id=evidence.evidence_id,
        incremental_update=update,
        decision_at=_NOW,
        assessed_at=_NOW,
        evidence_records=(evidence,),
        semantic_claims=(claim,),
    )

    assert result.status == ThesisAssessmentStatus.UNSUPPORTED_INPUT


def test_removed_evidence_not_material_to_scenario_is_not_material() -> None:
    """REMOVED_OR_MISSINGだが、当該ScenarioのNarrativeCaseが実際には
    参照していない場合はNOT_MATERIAL(D0106 §17)。"""
    old_evidence, old_claim, _, _, _ = _build_evidence(document_id="DOC1", text="他Scenario用の旧根拠。")
    assert old_evidence is not None
    update = build_incremental_research_update(
        prior_evidence_records=(old_evidence,), current_evidence_records=(), semantic_claims=(old_claim,)
    )
    # bear_caseのみが参照、base_caseは参照していない
    artifact = _research_artifact(
        "R1", included_evidence_ids=(old_evidence.evidence_id,), bear_evidence_ids=(old_evidence.evidence_id,)
    )

    result = assess_thesis_impact(
        research_artifact=artifact,
        scenario=ThesisScenario.BASE,
        evidence_id=old_evidence.evidence_id,
        incremental_update=update,
        decision_at=_NOW,
        assessed_at=_NOW,
    )

    assert result.status == ThesisAssessmentStatus.NOT_MATERIAL


def test_duplicate_evidence_id_in_pool_is_ambiguous() -> None:
    evidence, claim, _, _, _ = _build_evidence(document_id="DOC1", text="重複Evidenceテスト。")
    assert evidence is not None
    duplicate = type(evidence)(
        evidence_id=evidence.evidence_id,
        evidence_type=evidence.evidence_type,
        layer=evidence.layer,
        capability=evidence.capability,
        content="DIFFERENT CONTENT",
        source=evidence.source,
    )
    update = build_incremental_research_update(
        prior_evidence_records=(), current_evidence_records=(evidence,), semantic_claims=(claim,)
    )
    artifact = _research_artifact("R1", included_evidence_ids=())

    result = assess_thesis_impact(
        research_artifact=artifact,
        scenario=ThesisScenario.BASE,
        evidence_id=evidence.evidence_id,
        incremental_update=update,
        decision_at=_NOW,
        assessed_at=_NOW,
        evidence_records=(evidence, duplicate),
        semantic_claims=(claim,),
    )

    assert result.status == ThesisAssessmentStatus.AMBIGUOUS_REFERENCE


# ============================================================
# Code Review Finding(D0106)Closure
# ============================================================


def test_malformed_candidate_element_raises_schema_error_not_attribute_error() -> None:
    """`candidates`の要素が`SemanticClaimCandidate`でない場合、生の
    `AttributeError`を漏らさず`ThesisImpactSchemaError`で明示的に拒否
    する(D0105の`_require_type`と同じ方針)。"""
    evidence, claim, _candidate, norm_doc, document = _build_evidence(document_id="DOC1", text="不正Candidateテスト。")
    assert evidence is not None
    update = build_incremental_research_update(
        prior_evidence_records=(), current_evidence_records=(evidence,), semantic_claims=(claim,)
    )
    artifact = _research_artifact("R1", included_evidence_ids=())
    model = FakeThesisRelationModel(fixed_response=_relation_response(EvidenceRelation.SUPPORTS))

    with pytest.raises(ThesisImpactSchemaError):
        assess_thesis_impact(
            research_artifact=artifact,
            scenario=ThesisScenario.BASE,
            evidence_id=evidence.evidence_id,
            incremental_update=update,
            decision_at=_NOW,
            assessed_at=_NOW,
            evidence_records=(evidence,),
            semantic_claims=(claim,),
            candidates=({"malformed": True},),  # type: ignore[arg-type]
            normalized_documents=(norm_doc,),
            disclosure_documents=(document,),
            model=model,
            model_provider="test",
            model_name="test-model",
            prompt_hash="HASH1",
        )


def test_model_input_carries_actual_claim_type_and_direction() -> None:
    """Code Review Finding(D0106)Closure: `ThesisRelationModelInput.
    evidence_claim_type`/`evidence_direction`が固定`None`ではなく、
    実際のSemanticClaimから渡されることを確認する。"""
    evidence, claim, candidate, norm_doc, document = _build_evidence(
        document_id="DOC1",
        text="業績は増加する。",
        direction=ClaimDirection.INCREASE,
    )
    assert evidence is not None
    assert claim.claim_type == SemanticClaimType.BUSINESS_RISK
    assert claim.direction == ClaimDirection.INCREASE
    update = build_incremental_research_update(
        prior_evidence_records=(), current_evidence_records=(evidence,), semantic_claims=(claim,)
    )
    artifact = _research_artifact("R1", included_evidence_ids=())
    model = FakeThesisRelationModel(fixed_response=_relation_response(EvidenceRelation.SUPPORTS))

    assess_thesis_impact(
        research_artifact=artifact,
        scenario=ThesisScenario.BASE,
        evidence_id=evidence.evidence_id,
        incremental_update=update,
        decision_at=_NOW,
        assessed_at=_NOW,
        evidence_records=(evidence,),
        semantic_claims=(claim,),
        candidates=(candidate,),
        normalized_documents=(norm_doc,),
        disclosure_documents=(document,),
        model=model,
        model_provider="test",
        model_name="test-model",
        prompt_hash="HASH1",
    )

    assert model.call_count == 1
    sent_input = model.calls[0]
    assert sent_input.evidence_claim_type == SemanticClaimType.BUSINESS_RISK
    assert sent_input.evidence_direction == ClaimDirection.INCREASE


def test_empty_narrative_case_summary_is_typed_unsupported_input_not_exception() -> None:
    """Code Review Finding(D0106)Closure: 空の`NarrativeCase.summary`
    (Legitimate Domain State、ResearchArtifact側で構造的に禁止されて
    いない)は、`ThesisImpactSchemaError`をRaiseせず`UNSUPPORTED_INPUT`
    というTyped Outcomeを返す。"""
    evidence, claim, candidate, norm_doc, document = _build_evidence(document_id="DOC1", text="空Summaryテスト。")
    assert evidence is not None
    update = build_incremental_research_update(
        prior_evidence_records=(), current_evidence_records=(evidence,), semantic_claims=(claim,)
    )
    artifact = _research_artifact("R1", included_evidence_ids=())
    empty_summary_artifact = ResearchArtifact(
        **{
            **{f.name: getattr(artifact, f.name) for f in artifact.__dataclass_fields__.values()},
            "base_case": NarrativeCase(summary=""),
        }
    )
    model = FakeThesisRelationModel(fixed_response=_relation_response(EvidenceRelation.SUPPORTS))

    result = assess_thesis_impact(
        research_artifact=empty_summary_artifact,
        scenario=ThesisScenario.BASE,
        evidence_id=evidence.evidence_id,
        incremental_update=update,
        decision_at=_NOW,
        assessed_at=_NOW,
        evidence_records=(evidence,),
        semantic_claims=(claim,),
        candidates=(candidate,),
        normalized_documents=(norm_doc,),
        disclosure_documents=(document,),
        model=model,
        model_provider="test",
        model_name="test-model",
        prompt_hash="HASH1",
    )

    assert result.status == ThesisAssessmentStatus.UNSUPPORTED_INPUT
    assert result.assessment is None
    assert model.call_count == 0


def test_prompt_hash_required_when_model_supplied() -> None:
    evidence, claim, candidate, norm_doc, document = _build_evidence(document_id="DOC1", text="Prompt Hash必須テスト。")
    assert evidence is not None
    update = build_incremental_research_update(
        prior_evidence_records=(), current_evidence_records=(evidence,), semantic_claims=(claim,)
    )
    artifact = _research_artifact("R1", included_evidence_ids=())
    model = FakeThesisRelationModel(fixed_response=_relation_response(EvidenceRelation.SUPPORTS))

    with pytest.raises(ThesisImpactSchemaError):
        assess_thesis_impact(
            research_artifact=artifact,
            scenario=ThesisScenario.BASE,
            evidence_id=evidence.evidence_id,
            incremental_update=update,
            decision_at=_NOW,
            assessed_at=_NOW,
            evidence_records=(evidence,),
            semantic_claims=(claim,),
            candidates=(candidate,),
            normalized_documents=(norm_doc,),
            disclosure_documents=(document,),
            model=model,
            model_provider="test",
            model_name="test-model",
            prompt_hash="",
        )


# ============================================================
# Assessment Provenance (D0106 §19)
# ============================================================


def test_assessment_provenance_distinguishes_assessed_at_from_evidence_available_at() -> None:
    evidence, claim, candidate, norm_doc, document = _build_evidence(
        document_id="DOC1", text="Provenance分離テスト。", retrieved_at=datetime(2026, 1, 1, tzinfo=UTC)
    )
    assert evidence is not None
    update = build_incremental_research_update(
        prior_evidence_records=(), current_evidence_records=(evidence,), semantic_claims=(claim,)
    )
    artifact = _research_artifact("R1", included_evidence_ids=())
    assessed_at = datetime(2026, 9, 15, tzinfo=UTC)
    model = FakeThesisRelationModel(fixed_response=_relation_response(EvidenceRelation.SUPPORTS))

    result = assess_thesis_impact(
        research_artifact=artifact,
        scenario=ThesisScenario.BASE,
        evidence_id=evidence.evidence_id,
        incremental_update=update,
        decision_at=_NOW,
        assessed_at=assessed_at,
        evidence_records=(evidence,),
        semantic_claims=(claim,),
        candidates=(candidate,),
        normalized_documents=(norm_doc,),
        disclosure_documents=(document,),
        model=model,
        model_provider="prov",
        model_name="name",
        prompt_hash="HASH1",
    )

    _assert_assessed(result)
    assert result.assessment.assessed_at == assessed_at
    assert result.assessment.evidence_available_at == evidence.source.available_at
    assert result.assessment.evidence_available_at != assessed_at
    assert result.assessment.assessment_provenance is not None
    assert result.assessment.assessment_provenance.generated_at == assessed_at
    assert result.assessment.assessment_provenance.input_evidence_ids == (evidence.evidence_id,)
    assert result.assessment.lineage_reference == claim.claim_id


# ============================================================
# Potential Supersession (D0106 §13)
# ============================================================


def test_potentially_superseded_new_side_is_assessed_not_auto_invalidating() -> None:
    old_evidence, old_claim, _, _, _ = _build_evidence(document_id="DOC1", text="旧Claim。")
    assert old_evidence is not None
    new_norm_doc = _single_member_doc(_ix("jpcrp_cor:BusinessRisksTextBlock", "新Claim。"), document_id="DOC2")
    new_claim_candidate = _candidate(
        evidence_span=_span_for(new_norm_doc),
        normalized_claim_text="新Claim。",
    )
    new_claim = build_semantic_claim(
        claim_type=new_claim_candidate.claim_type,
        normalized_claim_text=new_claim_candidate.normalized_claim_text,
        direction=new_claim_candidate.direction,
        evidence_span=new_claim_candidate.evidence_span,
        faithfulness_outcome=FaithfulnessOutcome.ACCEPT,
        extraction_version=new_claim_candidate.extraction_version,
        schema_version=new_claim_candidate.schema_version,
        extraction_provenance=new_claim_candidate.extraction_provenance,
        supersedes_claim_id=old_claim.claim_id,
    )
    new_document = _disclosure_document(internal_document_id="DOC2", retrieved_at=datetime(2026, 9, 1, tzinfo=UTC))
    new_evidence = _evidence_for(new_claim, new_document)

    update = build_incremental_research_update(
        prior_evidence_records=(old_evidence,),
        current_evidence_records=(old_evidence, new_evidence),
        semantic_claims=(old_claim, new_claim),
    )
    assert len(update.potentially_superseded_pairs) == 1
    artifact = _research_artifact("R1", included_evidence_ids=())
    model = FakeThesisRelationModel(fixed_response=_relation_response(EvidenceRelation.UNKNOWN))

    result = assess_thesis_impact(
        research_artifact=artifact,
        scenario=ThesisScenario.BASE,
        evidence_id=new_evidence.evidence_id,
        incremental_update=update,
        decision_at=_NOW,
        assessed_at=_NOW,
        candidates=(new_claim_candidate,),
        normalized_documents=(new_norm_doc,),
        disclosure_documents=(new_document,),
        evidence_records=(old_evidence, new_evidence),
        semantic_claims=(old_claim, new_claim),
        model=model,
        model_provider="test",
        model_name="test-model",
        prompt_hash="HASH1",
    )

    _assert_assessed(result)
    assert result.assessment.evidence_change_kind == EvidenceChangeKind.POTENTIALLY_SUPERSEDED
    assert result.assessment.relation == EvidenceRelation.UNKNOWN


# ============================================================
# No LLM / No ResearchArtifact Mutation (Source Level)
# ============================================================


def test_thesis_impact_module_has_no_direct_model_wiring() -> None:
    source = Path(thesis_impact_module.__file__).read_text(encoding="utf-8")
    for forbidden in ("import openai", "import anthropic", "requests.post", "httpx."):
        assert forbidden not in source


def test_thesis_impact_module_never_constructs_research_artifact_or_narrative_case() -> None:
    source = Path(thesis_impact_module.__file__).read_text(encoding="utf-8")
    assert "ResearchArtifact(" not in source
    assert "NarrativeCase(" not in source


def test_thesis_impact_module_has_no_valuation_or_decision_logic() -> None:
    source = Path(thesis_impact_module.__file__).read_text(encoding="utf-8")
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
    for forbidden in ("BUY", "SELL", "expected_return", "valuation", "target_price", "position_siz", "PortfolioSiz"):
        assert forbidden not in joined


def test_result_type_is_immutable() -> None:
    result = assess_thesis_impact(
        research_artifact=_research_artifact("R1", included_evidence_ids=()),
        scenario=ThesisScenario.BASE,
        evidence_id="EVID_CLAIM_NONEXISTENT",
        incremental_update=IncrementalResearchUpdateResult(
            status=build_incremental_research_update(prior_evidence_records=(), current_evidence_records=()).status
        ),
        decision_at=_NOW,
        assessed_at=_NOW,
    )
    assert isinstance(result, ThesisImpactResult)
