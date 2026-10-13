"""`lib.disclosures.evidence_lineage`(D0104)のRegression Test。

`resolve_evidence_lineage()`/`evidence_ids_for_document()`が以下を機械的に
強制することを検証する:

1. EvidenceRecord -> SemanticClaim -> SemanticClaimCandidate -> TextBlock
   -> DisclosureDocumentのBackward Traversalが、実際のD0101.1/D0102.x/D0103
   Objectを使ったHappy Pathで完走すること(supporting quote/span/
   available_atの逐語保持を含む)。
2. 各段でLinkが0件(MISSING_LINK)・2件以上(AMBIGUOUS_LINK)・構造的不整合
   (IDENTITY_MISMATCH)・PIT Drift(PIT_MISMATCH)・対象外Provenance
   (UNSUPPORTED_PROVENANCE)のいずれも、Silent Repairせず常にFail Closed
   すること。
3. Forward Impact Query(`evidence_ids_for_document()`)が過剰Includeしない
   こと。
4. 本Moduleがいかなる意味でもModel呼び出し・ResearchArtifact/BUY/SELL/
   期待Return Logicを持たないこと(Source Level確認)。

Fixture方式は`test_evidence_integration.py`と同じ(Synthetic EDINET-shaped
ZIPを構築し、実際の`normalize_edinet_type1_zip()`経由でD0101.1の実
`EvidenceSpan`を得る)。`SemanticClaimCandidate`から`build_semantic_claim()`
へ渡すField(`claim_type`/`normalized_claim_text`/`direction`/
`evidence_span`/`extraction_version`/`schema_version`/
`extraction_provenance`)をそのままCopyすることで、
`lib.disclosures.faithfulness.promote_verified_candidate()`が実際に生成
するのと同じ形のSemanticClaimを構築する(Faithfulness 8軸Checkは本Test
Moduleの対象外のため`FaithfulnessVerificationResult`は構築しない)。
"""

from __future__ import annotations

import ast
import dataclasses
import io
import zipfile
from datetime import UTC, datetime
from pathlib import Path

from lib.disclosures import evidence_lineage as evidence_lineage_module
from lib.disclosures.candidate_extraction import SCHEMA_VERSION as CANDIDATE_SCHEMA_VERSION
from lib.disclosures.candidate_extraction import SemanticClaimCandidate
from lib.disclosures.evidence_integration import integrate_accepted_semantic_claim
from lib.disclosures.evidence_lineage import (
    EvidenceLineage,
    EvidenceLineageStatus,
    evidence_ids_for_document,
    resolve_evidence_lineage,
)
from lib.disclosures.faithfulness import compute_candidate_reference
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
from lib.evidence.model import AiDerivedProvenance, AvailabilityBasis, EvidenceRecord, EvidenceType
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


def _normalize(raw_zip: bytes, *, document_id: str = "DOC1") -> NormalizedDisclosureDocument:
    return normalize_edinet_type1_zip(document_id=document_id, raw_zip_bytes=raw_zip)


def _single_member_doc(body_inner: str, *, document_id: str = "DOC1") -> NormalizedDisclosureDocument:
    raw_zip = _build_zip({_BODY_PATH: _htm(body_inner)})
    return _normalize(raw_zip, document_id=document_id)


def _span_for(doc: NormalizedDisclosureDocument, *, occurrence: int = 0) -> EvidenceSpan:
    member = doc.members[0]
    return EvidenceSpan.from_text_block(document=doc, member=member, text_block=member.text_blocks[occurrence])


def _provenance(*, generated_at: datetime = datetime(2026, 1, 1, tzinfo=UTC)) -> AiDerivedProvenance:
    return AiDerivedProvenance(
        model_provider="test-provider",
        model_name="test-model",
        model_version="v1",
        generated_at=generated_at,
    )


def _candidate(
    *,
    evidence_span: EvidenceSpan,
    claim_type: SemanticClaimType = SemanticClaimType.BUSINESS_RISK,
    normalized_claim_text: str = "重要な変更はありません。",
    direction: ClaimDirection = ClaimDirection.UNSPECIFIED,
    extraction_version: str = "EXTRACT_V1",
    extraction_provenance: AiDerivedProvenance | None = None,
    schema_version: str = CANDIDATE_SCHEMA_VERSION,
) -> SemanticClaimCandidate:
    return SemanticClaimCandidate(
        claim_type=claim_type,
        normalized_claim_text=normalized_claim_text,
        direction=direction,
        evidence_span=evidence_span,
        extraction_version=extraction_version,
        extraction_provenance=extraction_provenance if extraction_provenance is not None else _provenance(),
        schema_version=schema_version,
    )


def _claim_from_candidate(
    candidate: SemanticClaimCandidate, *, faithfulness_outcome: FaithfulnessOutcome = FaithfulnessOutcome.ACCEPT
) -> SemanticClaim:
    # `lib.disclosures.faithfulness.promote_verified_candidate()`が実際に
    # 行うのと同じField Copy(値を一切変更しない)。
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
    market_public_at: datetime | None = None,
    provider_available_at: datetime | None = None,
    provider_available_at_basis: AvailabilityBasis = AvailabilityBasis.UNKNOWN,
    retrieved_at: datetime = datetime(2026, 8, 17, 15, 6, tzinfo=UTC),
    provenance_id: str | None = None,
    source_document_id: str | None = "S1",
) -> DisclosureDocument:
    return DisclosureDocument(
        internal_document_id=internal_document_id,
        source_document_id=source_document_id,
        entity_id=entity_id,
        title="半期報告書",
        originating_source="EDINET",
        delivery_provider="EDINET",
        market_public_at=market_public_at,
        market_public_at_basis=(AvailabilityBasis.EXACT if market_public_at is not None else AvailabilityBasis.UNKNOWN),
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


def _happy_path() -> tuple[
    EvidenceRecord, SemanticClaim, SemanticClaimCandidate, NormalizedDisclosureDocument, DisclosureDocument
]:
    norm_doc = _single_member_doc(_ix("jpcrp_cor:BusinessRisksTextBlock", "重要な変更はありません。"))
    candidate = _candidate(evidence_span=_span_for(norm_doc))
    claim = _claim_from_candidate(candidate)
    document = _disclosure_document()
    evidence = _evidence_for(claim, document)
    return evidence, claim, candidate, norm_doc, document


# --- A/B/C: Happy Path Backward Traversal ------------------------------------


def test_happy_path_full_backward_lineage() -> None:
    evidence, claim, candidate, norm_doc, document = _happy_path()

    result = resolve_evidence_lineage(
        evidence,
        semantic_claims=(claim,),
        candidates=(candidate,),
        normalized_documents=(norm_doc,),
        disclosure_documents=(document,),
    )

    assert result.status == EvidenceLineageStatus.SUCCESS
    assert isinstance(result.lineage, EvidenceLineage)
    lineage = result.lineage
    assert lineage.evidence_id == evidence.evidence_id
    assert lineage.claim_id == claim.claim_id
    assert lineage.semantic_identity_key == claim.semantic_identity_key
    assert lineage.document_id == "DOC1"
    assert lineage.entity_id == "7203"
    assert lineage.faithfulness_outcome is FaithfulnessOutcome.ACCEPT


def test_supporting_quote_and_span_preserved_exactly() -> None:
    evidence, claim, candidate, norm_doc, document = _happy_path()

    result = resolve_evidence_lineage(
        evidence,
        semantic_claims=(claim,),
        candidates=(candidate,),
        normalized_documents=(norm_doc,),
        disclosure_documents=(document,),
    )

    assert result.lineage is not None
    span = claim.evidence_span
    assert result.lineage.supporting_quote == span.supporting_quote == "重要な変更はありません。"
    assert result.lineage.member_path == span.member_path
    assert result.lineage.taxonomy_element_name == span.taxonomy_element_name
    assert result.lineage.occurrence_index == span.occurrence_index
    assert result.lineage.char_start == span.char_start
    assert result.lineage.char_end == span.char_end


def test_available_at_preserved_correctly() -> None:
    norm_doc = _single_member_doc(_ix("jpcrp_cor:BusinessRisksTextBlock", "重要な変更はありません。"))
    candidate = _candidate(evidence_span=_span_for(norm_doc))
    claim = _claim_from_candidate(candidate)
    provider_available_at = datetime(2026, 8, 17, 15, 2, tzinfo=UTC)
    document = _disclosure_document(
        provider_available_at=provider_available_at, provider_available_at_basis=AvailabilityBasis.EXACT
    )
    evidence = _evidence_for(claim, document)

    result = resolve_evidence_lineage(
        evidence,
        semantic_claims=(claim,),
        candidates=(candidate,),
        normalized_documents=(norm_doc,),
        disclosure_documents=(document,),
    )

    assert result.status == EvidenceLineageStatus.SUCCESS
    assert result.lineage is not None
    assert result.lineage.available_at == provider_available_at == evidence.source.available_at


# --- D/E/F/G: Fail-Closed Missing Link ---------------------------------------


def test_missing_semantic_claim_fails_closed() -> None:
    evidence, claim, candidate, norm_doc, document = _happy_path()

    result = resolve_evidence_lineage(
        evidence, semantic_claims=(), candidates=(candidate,), normalized_documents=(norm_doc,), disclosure_documents=(document,)
    )

    assert result.status == EvidenceLineageStatus.MISSING_LINK
    assert result.lineage is None
    assert result.reason is not None


def test_missing_candidate_fails_closed() -> None:
    evidence, claim, candidate, norm_doc, document = _happy_path()

    result = resolve_evidence_lineage(
        evidence, semantic_claims=(claim,), candidates=(), normalized_documents=(norm_doc,), disclosure_documents=(document,)
    )

    assert result.status == EvidenceLineageStatus.MISSING_LINK
    assert result.lineage is None
    assert "D0103-R-01" in (result.reason or "")


def test_missing_normalized_document_fails_closed() -> None:
    evidence, claim, candidate, norm_doc, document = _happy_path()

    result = resolve_evidence_lineage(
        evidence, semantic_claims=(claim,), candidates=(candidate,), normalized_documents=(), disclosure_documents=(document,)
    )

    assert result.status == EvidenceLineageStatus.MISSING_LINK
    assert result.lineage is None


def test_textblock_content_drift_fails_closed_as_identity_mismatch() -> None:
    """F: TextBlockが現在のDocument内容と食い違う場合(Content Drift)、
    `revalidate_evidence_span()`の`NEEDS_REVALIDATION`経由でFail Closed
    する。"""
    evidence, claim, candidate, _norm_doc, document = _happy_path()
    # 同じdocument_idだが実際のBody内容が異なる(raw_canonical_content_hash
    # が変わる)Documentを渡す——TextBlockのOffset/Quoteが現在のDocumentと
    # 整合しない状態を再現する。
    drifted_doc = _single_member_doc(_ix("jpcrp_cor:BusinessRisksTextBlock", "内容が変更されました。"))

    result = resolve_evidence_lineage(
        evidence,
        semantic_claims=(claim,),
        candidates=(candidate,),
        normalized_documents=(drifted_doc,),
        disclosure_documents=(document,),
    )

    assert result.status == EvidenceLineageStatus.IDENTITY_MISMATCH
    assert result.lineage is None


def test_missing_disclosure_document_fails_closed() -> None:
    evidence, claim, candidate, norm_doc, _document = _happy_path()

    result = resolve_evidence_lineage(
        evidence, semantic_claims=(claim,), candidates=(candidate,), normalized_documents=(norm_doc,), disclosure_documents=()
    )

    assert result.status == EvidenceLineageStatus.MISSING_LINK
    assert result.lineage is None


# --- H/I: Identity / Ambiguity -----------------------------------------------


def test_document_identity_mismatch_via_entity_id_fails() -> None:
    """H: internal_document_idは一致するが、entity_idがevidence.
    related_codesと矛盾するDisclosureDocument(別会社のDocumentへの
    取り違えを模擬)はIDENTITY_MISMATCHになる。"""
    evidence, claim, candidate, norm_doc, document = _happy_path()
    wrong_entity_document = dataclasses.replace(document, entity_id="9999")

    result = resolve_evidence_lineage(
        evidence,
        semantic_claims=(claim,),
        candidates=(candidate,),
        normalized_documents=(norm_doc,),
        disclosure_documents=(wrong_entity_document,),
    )

    assert result.status == EvidenceLineageStatus.IDENTITY_MISMATCH
    assert result.lineage is None


def test_document_identity_mismatch_detected_even_when_entity_id_absent_on_original() -> None:
    """Code Review Finding(D0104)Closure: Evidence作成時点のDocumentが
    `entity_id=None`だった(`evidence.related_codes == ()`)としても、
    後から渡されたDisclosureDocumentが`entity_id`を持つ(=別Documentへの
    取り違えの可能性)場合はIDENTITY_MISMATCHになる——`evidence.
    related_codes`が空だからという理由でCheckをSilent Skipしない。"""
    norm_doc = _single_member_doc(_ix("jpcrp_cor:BusinessRisksTextBlock", "重要な変更はありません。"))
    candidate = _candidate(evidence_span=_span_for(norm_doc))
    claim = _claim_from_candidate(candidate)
    original_document = _disclosure_document(entity_id=None)
    evidence = _evidence_for(claim, original_document)
    assert evidence.related_codes == ()

    substituted_document = _disclosure_document(entity_id="9999")

    result = resolve_evidence_lineage(
        evidence,
        semantic_claims=(claim,),
        candidates=(candidate,),
        normalized_documents=(norm_doc,),
        disclosure_documents=(substituted_document,),
    )

    assert result.status == EvidenceLineageStatus.IDENTITY_MISMATCH
    assert result.lineage is None


def test_document_identity_mismatch_detected_via_provenance_id_even_when_absent_on_original() -> None:
    """Code Review Finding(D0104)Closure: 同様に`provenance_id`側も
    Bidirectionalに検証する(一方がNoneだからという理由でSilent Skip
    しない)。"""
    norm_doc = _single_member_doc(_ix("jpcrp_cor:BusinessRisksTextBlock", "重要な変更はありません。"))
    candidate = _candidate(evidence_span=_span_for(norm_doc))
    claim = _claim_from_candidate(candidate)
    original_document = _disclosure_document(provenance_id=None)
    evidence = _evidence_for(claim, original_document)
    assert evidence.provenance_id is None

    substituted_document = _disclosure_document(provenance_id="PROV_WRONG")

    result = resolve_evidence_lineage(
        evidence,
        semantic_claims=(claim,),
        candidates=(candidate,),
        normalized_documents=(norm_doc,),
        disclosure_documents=(substituted_document,),
    )

    assert result.status == EvidenceLineageStatus.IDENTITY_MISMATCH
    assert result.lineage is None


def test_ambiguous_duplicate_claim_id_fails() -> None:
    """I: 同一claim_idを持つSemanticClaimが2件存在する場合、どちらかを
    無言で選択せずAMBIGUOUS_LINKにする。"""
    evidence, claim, candidate, norm_doc, document = _happy_path()

    result = resolve_evidence_lineage(
        evidence,
        semantic_claims=(claim, claim),
        candidates=(candidate,),
        normalized_documents=(norm_doc,),
        disclosure_documents=(document,),
    )

    assert result.status == EvidenceLineageStatus.AMBIGUOUS_LINK
    assert result.lineage is None


def test_ambiguous_duplicate_candidate_fails() -> None:
    evidence, claim, candidate, norm_doc, document = _happy_path()

    result = resolve_evidence_lineage(
        evidence,
        semantic_claims=(claim,),
        candidates=(candidate, candidate),
        normalized_documents=(norm_doc,),
        disclosure_documents=(document,),
    )

    assert result.status == EvidenceLineageStatus.AMBIGUOUS_LINK
    assert result.lineage is None


# --- J: PIT Mismatch ----------------------------------------------------------


def test_pit_available_at_drift_fails_closed() -> None:
    evidence, claim, candidate, norm_doc, document = _happy_path()
    tampered_source = dataclasses.replace(evidence.source, available_at=datetime(2099, 1, 1, tzinfo=UTC))
    tampered_evidence = dataclasses.replace(evidence, source=tampered_source)

    result = resolve_evidence_lineage(
        tampered_evidence,
        semantic_claims=(claim,),
        candidates=(candidate,),
        normalized_documents=(norm_doc,),
        disclosure_documents=(document,),
    )

    assert result.status == EvidenceLineageStatus.PIT_MISMATCH
    assert result.lineage is None


# --- K/L: Forward Impact Query ------------------------------------------------


def test_forward_query_returns_descendant_evidence_ids() -> None:
    evidence, claim, _candidate, _norm_doc, _document = _happy_path()

    result = evidence_ids_for_document("DOC1", evidence_records=(evidence,), semantic_claims=(claim,))

    assert result == (evidence.evidence_id,)


def test_forward_query_excludes_unrelated_evidence() -> None:
    evidence_a, claim_a, _ca, _na, _da = _happy_path()

    norm_doc_b = _single_member_doc(_ix("jpcrp_cor:BusinessRisksTextBlock", "別のDocument。"), document_id="DOC2")
    candidate_b = _candidate(evidence_span=_span_for(norm_doc_b))
    claim_b = _claim_from_candidate(candidate_b)
    document_b = _disclosure_document(internal_document_id="DOC2")
    evidence_b = _evidence_for(claim_b, document_b)

    result = evidence_ids_for_document("DOC1", evidence_records=(evidence_a, evidence_b), semantic_claims=(claim_a, claim_b))

    assert result == (evidence_a.evidence_id,)
    assert evidence_b.evidence_id not in result


def test_forward_query_excludes_evidence_whose_matched_claim_is_not_accepted() -> None:
    """Code Review Finding(D0104)Closure: claim_idはfaithfulness_outcome
    を含まずに決定論的に導出されるため、同じclaim_idを持つACCEPT/
    REVIEW_REQUIRED双方のClaimがsemantic_claimsに混在しうる。Forward
    Queryは`resolve_evidence_lineage()`と同じACCEPT-only Gateを独立に
    適用し、REVIEW_REQUIRED側しか見つからない場合はEvidenceを含めない
    (resolve_evidence_lineage()がUNSUPPORTED_PROVENANCEとして拒否する
    Caseと、Forward Queryの基準を一致させる)。"""
    norm_doc = _single_member_doc(_ix("jpcrp_cor:BusinessRisksTextBlock", "重要な変更はありません。"))
    candidate = _candidate(evidence_span=_span_for(norm_doc))
    accept_claim = _claim_from_candidate(candidate, faithfulness_outcome=FaithfulnessOutcome.ACCEPT)
    review_required_claim = _claim_from_candidate(candidate, faithfulness_outcome=FaithfulnessOutcome.REVIEW_REQUIRED)
    assert accept_claim.claim_id == review_required_claim.claim_id
    document = _disclosure_document()
    evidence = _evidence_for(accept_claim, document)

    result = evidence_ids_for_document("DOC1", evidence_records=(evidence,), semantic_claims=(review_required_claim,))

    assert result == ()


# --- M/N: Infrastructure Boundary (Source-Level Static Checks) --------------


def test_evidence_lineage_module_has_no_model_dependency() -> None:
    # M: Lineage Traversal自体はいかなる意味でもModel/LLM呼び出しを
    # 必要としない(Source Level確認、D0104 §2)。
    source = Path(evidence_lineage_module.__file__).read_text(encoding="utf-8")
    for forbidden in ("CandidateExtractionModel", "FaithfulnessVerifier", ".extract(", "import openai", "import anthropic"):
        assert forbidden not in source


def test_evidence_lineage_module_has_no_research_artifact_or_decision_logic() -> None:
    # N: ResearchArtifact/NarrativeCase生成・Bull/Base/Bear・SUPPORTS/
    # CONTRADICTS・Confidence・期待Return・BUY/SELL・Position Sizingは
    # いずれも本ModuleのCode自体(Docstring/Commentの説明文を除く、AST
    # Identifier/Attribute/Import/String Literalのみ)に一切存在しない
    # (D0104 §9 Research Layer Boundary)。
    source = Path(evidence_lineage_module.__file__).read_text(encoding="utf-8")
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
    # Docstring/Comment中の説明文(Constant String)は意図的に対象外にする
    # (例: 「本Moduleは...ResearchArtifact生成...を一切行わない」という
    # 説明自体がString Literalとして検出され、Boundary不遵守と誤検知される
    # ため)。Name/Attribute/引数名/関数・クラス名/Import名のみを見る。
    joined_identifiers = " ".join(identifiers)
    forbidden_terms = (
        "ResearchArtifact",
        "NarrativeCase",
        "Bull",
        "Bear",
        "SUPPORTS",
        "CONTRADICTS",
        "confidence",
        "expected_return",
        "BUY",
        "SELL",
        "position_siz",
    )
    for forbidden in forbidden_terms:
        assert forbidden not in joined_identifiers


def test_resolve_evidence_lineage_rejects_non_claim_evidence_type() -> None:
    evidence, claim, candidate, norm_doc, document = _happy_path()
    non_claim_evidence = dataclasses.replace(evidence, evidence_id="EVID_FACT_X", evidence_type=EvidenceType.FACT)

    result = resolve_evidence_lineage(
        non_claim_evidence,
        semantic_claims=(claim,),
        candidates=(candidate,),
        normalized_documents=(norm_doc,),
        disclosure_documents=(document,),
    )

    assert result.status == EvidenceLineageStatus.UNSUPPORTED_PROVENANCE


def test_resolve_evidence_lineage_rejects_review_required_claim() -> None:
    # claim_id は semantic_identity_key + extraction_version のみから決定論的
    # に導出され、faithfulness_outcome を含まない(D0102.1 §F)。そのため
    # evidence.source.source_id(== accept_claim.claim_id)での検索は、同じ
    # claim_idを持つREVIEW_REQUIREDのClaimにも一致してしまう——Resolver自身が
    # 独立に`faithfulness_outcome is ACCEPT`をここでもFail Closedで再確認する
    # ことを検証する(D0103 ACCEPT-only Gateの迂回をここでも許さない)。
    norm_doc = _single_member_doc(_ix("jpcrp_cor:BusinessRisksTextBlock", "重要な変更はありません。"))
    candidate = _candidate(evidence_span=_span_for(norm_doc))
    review_required_claim = _claim_from_candidate(candidate, faithfulness_outcome=FaithfulnessOutcome.REVIEW_REQUIRED)
    accept_claim = _claim_from_candidate(candidate, faithfulness_outcome=FaithfulnessOutcome.ACCEPT)
    assert review_required_claim.claim_id == accept_claim.claim_id
    document = _disclosure_document()
    evidence = _evidence_for(accept_claim, document)

    result = resolve_evidence_lineage(
        evidence,
        semantic_claims=(review_required_claim,),
        candidates=(candidate,),
        normalized_documents=(norm_doc,),
        disclosure_documents=(document,),
    )

    assert result.status == EvidenceLineageStatus.UNSUPPORTED_PROVENANCE
    assert result.lineage is None


# --- O: D0102.4 / D0103 既存Behavior不変 (Static Boundary Check) ------------


def test_evidence_lineage_does_not_modify_frozen_phase1_modules() -> None:
    # O: D0104はFrozen Phase1 Module自体を一切変更しない——Import元
    # としてのみ参照する(`lib.disclosures.faithfulness.
    # compute_candidate_reference`・`lib.disclosures.semantic_claims.
    # revalidate_evidence_span`等、既存公開APIの呼び出しのみ)。
    source = Path(evidence_lineage_module.__file__).read_text(encoding="utf-8")
    assert "def compute_candidate_reference" not in source
    assert "def revalidate_evidence_span" not in source
    assert "def build_semantic_claim" not in source


# ============================================================
# D0104.1 — Candidate Lineage Identity Hardening
#
# SemanticClaim -> SemanticClaimCandidateは唯一の「再構成された」Edge
# だった(compute_candidate_reference()が使う4 Fieldのみでの照合は、
# 同一EvidenceSpanに対する別Extraction Runが偶然同一Claim内容を生成
# したCaseを誤ってAmbiguousにしてしまう——SAFEだがAUDITABLEではない)。
# 以下はPromotion Boundaryが既にCopy済みの残り3 Field
# (extraction_version/schema_version/extraction_provenance)も使う
# 7 Field照合が、この偽Ambiguityを解消しつつ、本来のAmbiguity・
# Cross-Document/Cross-TextBlock取り違えは引き続きFail Closedする
# ことを証明する。
# ============================================================


def test_repeated_extraction_run_with_identical_content_resolves_without_false_ambiguity() -> None:
    """D0104.1の核心Regression: 同一EvidenceSpanに対し、異なる
    extraction_version(=別のExtraction Run)から生成された2つの
    Candidateが偶然同一のclaim_type/text/directionを持つ場合(定型文
    Claimが再Extractionされた典型Case、D0105 Incremental Research
    Updateが前提とするシナリオ)、4 Field照合ならAMBIGUOUS_LINKに
    なっていたが、7 Field照合では実際に対応するCandidate(Claimの
    extraction_version/schema_version/extraction_provenanceと一致する
    方)のみに一意に解決される。"""
    norm_doc = _single_member_doc(_ix("jpcrp_cor:BusinessRisksTextBlock", "重要な変更はありません。"))
    span = _span_for(norm_doc)

    candidate_run1 = _candidate(
        evidence_span=span,
        extraction_version="EXTRACT_V1",
        extraction_provenance=_provenance(generated_at=datetime(2026, 1, 1, tzinfo=UTC)),
    )
    candidate_run2 = _candidate(
        evidence_span=span,
        extraction_version="EXTRACT_V2",
        extraction_provenance=_provenance(generated_at=datetime(2026, 2, 1, tzinfo=UTC)),
    )
    # 両CandidateはEvidenceSpan/claim_type/normalized_claim_text/direction
    # が完全に同一(定型文の再Extraction)。
    assert candidate_run1.evidence_span == candidate_run2.evidence_span
    assert candidate_run1.claim_type == candidate_run2.claim_type
    assert candidate_run1.normalized_claim_text == candidate_run2.normalized_claim_text
    assert candidate_run1.direction == candidate_run2.direction
    assert candidate_run1.extraction_version != candidate_run2.extraction_version

    claim = _claim_from_candidate(candidate_run2)
    document = _disclosure_document()
    evidence = _evidence_for(claim, document)

    result = resolve_evidence_lineage(
        evidence,
        semantic_claims=(claim,),
        candidates=(candidate_run1, candidate_run2),
        normalized_documents=(norm_doc,),
        disclosure_documents=(document,),
    )

    assert result.status == EvidenceLineageStatus.SUCCESS
    assert result.lineage is not None
    assert result.lineage.extraction_version == "EXTRACT_V2"


def test_true_duplicate_candidate_across_identical_runs_still_ambiguous() -> None:
    """Sanity Check: extraction_version/extraction_provenanceまで含めて
    完全に同一の2つのCandidate(真のDuplicate、発生すべきではないが
    Caller側のBugを想定)は、7 Field照合でも依然AMBIGUOUS_LINKになる
    (任意選択はしない)。"""
    norm_doc = _single_member_doc(_ix("jpcrp_cor:BusinessRisksTextBlock", "重要な変更はありません。"))
    candidate = _candidate(evidence_span=_span_for(norm_doc))
    duplicate_candidate = _candidate(evidence_span=_span_for(norm_doc))
    assert candidate == duplicate_candidate  # 完全に同一のCandidate
    claim = _claim_from_candidate(candidate)
    document = _disclosure_document()
    evidence = _evidence_for(claim, document)

    result = resolve_evidence_lineage(
        evidence,
        semantic_claims=(claim,),
        candidates=(candidate, duplicate_candidate),
        normalized_documents=(norm_doc,),
        disclosure_documents=(document,),
    )

    assert result.status == EvidenceLineageStatus.AMBIGUOUS_LINK
    assert result.lineage is None


def test_same_claim_text_from_different_document_cannot_cross_link() -> None:
    """A: 同一のClaim Text/claim_type/directionを持つCandidateが別
    Documentから来ている場合、EvidenceSpan.document_idが異なるため
    Cross-Linkしない(MISSING_LINK、Silent SUCCESSしない)。"""
    norm_doc_a = _single_member_doc(_ix("jpcrp_cor:BusinessRisksTextBlock", "重要な変更はありません。"), document_id="DOC1")
    norm_doc_b = _single_member_doc(_ix("jpcrp_cor:BusinessRisksTextBlock", "重要な変更はありません。"), document_id="DOC2")
    candidate_a = _candidate(evidence_span=_span_for(norm_doc_a))
    candidate_b = _candidate(evidence_span=_span_for(norm_doc_b))
    assert candidate_a.normalized_claim_text == candidate_b.normalized_claim_text
    assert candidate_a.evidence_span != candidate_b.evidence_span

    claim_a = _claim_from_candidate(candidate_a)
    document_a = _disclosure_document(internal_document_id="DOC1")
    evidence_a = _evidence_for(claim_a, document_a)

    result = resolve_evidence_lineage(
        evidence_a,
        semantic_claims=(claim_a,),
        candidates=(candidate_b,),  # DOC2由来のCandidateのみ(DOC1由来を含めない)
        normalized_documents=(norm_doc_a,),
        disclosure_documents=(document_a,),
    )

    assert result.status == EvidenceLineageStatus.MISSING_LINK
    assert result.lineage is None


def test_same_claim_text_from_different_textblock_cannot_cross_link() -> None:
    """B: 同一Document内に同一Taxonomy要素名・同一Textが2回出現する
    場合(occurrence_index 0/1)、Candidate側がoccurrence=1由来でも
    Claim側がoccurrence=0由来なら、EvidenceSpanのoccurrence_indexが
    異なるためCross-Linkしない。"""
    body = _ix("jpcrp_cor:BusinessRisksTextBlock", "重要な変更はありません。") + _ix(
        "jpcrp_cor:BusinessRisksTextBlock", "重要な変更はありません。"
    )
    norm_doc = _single_member_doc(body)
    assert len(norm_doc.members[0].text_blocks) == 2

    span_occurrence_0 = _span_for(norm_doc, occurrence=0)
    span_occurrence_1 = _span_for(norm_doc, occurrence=1)
    assert span_occurrence_0.occurrence_index != span_occurrence_1.occurrence_index
    assert span_occurrence_0 != span_occurrence_1

    candidate_occurrence_1 = _candidate(evidence_span=span_occurrence_1)
    claim_occurrence_0 = _claim_from_candidate(_candidate(evidence_span=span_occurrence_0))
    document = _disclosure_document()
    evidence = _evidence_for(claim_occurrence_0, document)

    result = resolve_evidence_lineage(
        evidence,
        semantic_claims=(claim_occurrence_0,),
        candidates=(candidate_occurrence_1,),
        normalized_documents=(norm_doc,),
        disclosure_documents=(document,),
    )

    assert result.status == EvidenceLineageStatus.MISSING_LINK
    assert result.lineage is None


def test_candidate_identity_match_survives_serialization_round_trip() -> None:
    """E: Candidate/EvidenceSpan/AiDerivedProvenanceはいずれもFrozen
    Dataclass(構造的Equality)であり、JSON等を介したSerialize/
    Deserializeで再構築された「別Instance」でもField値が保存されて
    いれば一致判定は成立する(Object Identityではなく値に基づく)。"""
    norm_doc = _single_member_doc(_ix("jpcrp_cor:BusinessRisksTextBlock", "重要な変更はありません。"))
    original_candidate = _candidate(evidence_span=_span_for(norm_doc))
    claim = _claim_from_candidate(original_candidate)
    document = _disclosure_document()
    evidence = _evidence_for(claim, document)

    # Serialize/Deserialize相当: 全FieldをPrimitive値へ変換し、同じ値から
    # 新しいInstanceを再構築する(実際にJSON round-tripしても同値になる
    # Primitive Typeのみで構成されていることを確認する)。
    rebuilt_span = EvidenceSpan(
        document_id=original_candidate.evidence_span.document_id,
        source_raw_canonical_content_hash=original_candidate.evidence_span.source_raw_canonical_content_hash,
        source_normalizer_version=original_candidate.evidence_span.source_normalizer_version,
        member_path=original_candidate.evidence_span.member_path,
        taxonomy_element_name=original_candidate.evidence_span.taxonomy_element_name,
        occurrence_index=original_candidate.evidence_span.occurrence_index,
        char_start=original_candidate.evidence_span.char_start,
        char_end=original_candidate.evidence_span.char_end,
        supporting_quote=original_candidate.evidence_span.supporting_quote,
    )
    rebuilt_provenance = AiDerivedProvenance(
        model_provider=original_candidate.extraction_provenance.model_provider,
        model_name=original_candidate.extraction_provenance.model_name,
        model_version=original_candidate.extraction_provenance.model_version,
        generated_at=original_candidate.extraction_provenance.generated_at,
    )
    rebuilt_candidate = SemanticClaimCandidate(
        claim_type=original_candidate.claim_type,
        normalized_claim_text=original_candidate.normalized_claim_text,
        direction=original_candidate.direction,
        evidence_span=rebuilt_span,
        extraction_version=original_candidate.extraction_version,
        extraction_provenance=rebuilt_provenance,
    )
    assert rebuilt_candidate is not original_candidate
    assert rebuilt_candidate == original_candidate

    result = resolve_evidence_lineage(
        evidence,
        semantic_claims=(claim,),
        candidates=(rebuilt_candidate,),
        normalized_documents=(norm_doc,),
        disclosure_documents=(document,),
    )

    assert result.status == EvidenceLineageStatus.SUCCESS
    assert result.lineage is not None
    assert result.lineage.candidate_reference == compute_candidate_reference(original_candidate)


def test_schema_version_divergence_alone_distinguishes_candidates() -> None:
    """Code Review Finding(D0104.1)Closure: `schema_version`のみが異なる
    2つのCandidate(他の6 Fieldは完全同一)が、正しく区別されることを
    独立に証明する——これが無ければ`_candidate_matches_claim()`から
    `schema_version`比較が将来誤って削除されても、既存Testは検知
    できなかった(他の全Testはextraction_versionの違いでのみ区別して
    いたため)。"""
    norm_doc = _single_member_doc(_ix("jpcrp_cor:BusinessRisksTextBlock", "重要な変更はありません。"))
    span = _span_for(norm_doc)
    candidate_a = _candidate(evidence_span=span, schema_version=CANDIDATE_SCHEMA_VERSION)
    candidate_b = _candidate(evidence_span=span, schema_version="OTHER_SCHEMA_V2")
    # 7 Field中、schema_versionのみが異なる。
    assert candidate_a.evidence_span == candidate_b.evidence_span
    assert candidate_a.claim_type == candidate_b.claim_type
    assert candidate_a.normalized_claim_text == candidate_b.normalized_claim_text
    assert candidate_a.direction == candidate_b.direction
    assert candidate_a.extraction_version == candidate_b.extraction_version
    assert candidate_a.extraction_provenance == candidate_b.extraction_provenance
    assert candidate_a.schema_version != candidate_b.schema_version

    claim = _claim_from_candidate(candidate_a)
    document = _disclosure_document()
    evidence = _evidence_for(claim, document)

    result = resolve_evidence_lineage(
        evidence,
        semantic_claims=(claim,),
        candidates=(candidate_a, candidate_b),
        normalized_documents=(norm_doc,),
        disclosure_documents=(document,),
    )

    # schema_version比較が機能していれば、candidate_bはMatchせず
    # candidate_aのみが一意にMatchしてSUCCESSになる(schema_version
    # 比較が削除されていれば両方Matchし誤ってAMBIGUOUS_LINKになる)。
    assert result.status == EvidenceLineageStatus.SUCCESS
    assert result.lineage is not None


def test_extraction_provenance_divergence_alone_distinguishes_candidates() -> None:
    """Code Review Finding(D0104.1)Closure: `extraction_provenance`のみ
    (`generated_at`)が異なる2つのCandidateが、正しく区別されることを
    独立に証明する(他の6 Fieldは完全同一)。"""
    norm_doc = _single_member_doc(_ix("jpcrp_cor:BusinessRisksTextBlock", "重要な変更はありません。"))
    span = _span_for(norm_doc)
    candidate_a = _candidate(evidence_span=span, extraction_provenance=_provenance(generated_at=datetime(2026, 1, 1, tzinfo=UTC)))
    candidate_b = _candidate(evidence_span=span, extraction_provenance=_provenance(generated_at=datetime(2026, 6, 1, tzinfo=UTC)))
    assert candidate_a.evidence_span == candidate_b.evidence_span
    assert candidate_a.claim_type == candidate_b.claim_type
    assert candidate_a.normalized_claim_text == candidate_b.normalized_claim_text
    assert candidate_a.direction == candidate_b.direction
    assert candidate_a.extraction_version == candidate_b.extraction_version
    assert candidate_a.schema_version == candidate_b.schema_version
    assert candidate_a.extraction_provenance != candidate_b.extraction_provenance

    claim = _claim_from_candidate(candidate_a)
    document = _disclosure_document()
    evidence = _evidence_for(claim, document)

    result = resolve_evidence_lineage(
        evidence,
        semantic_claims=(claim,),
        candidates=(candidate_a, candidate_b),
        normalized_documents=(norm_doc,),
        disclosure_documents=(document,),
    )

    assert result.status == EvidenceLineageStatus.SUCCESS
    assert result.lineage is not None
