"""`lib.disclosures.faithfulness`(Stage 3.18.6、D0102.4.1)のRegression
Test。

D0102.4/D0102.4A(DECISIONS.md、`READY_FOR_IMPLEMENTATION`)で承認された
Deterministic Core Architectureをそのまま検証する。実LLM/Vendor SDKへの
接続は一切行わない(`MODEL_CALL_SITES = 0`、D0102.4.2はこのModuleに
存在しない)。Fixture方式は`test_candidate_extraction.py`と同じ
(Synthetic EDINET-shaped ZIPを構築し、実際の`normalize_edinet_type1_zip()`
経由でD0101.1の実Objectを得る)。
"""

from __future__ import annotations

import io
import zipfile
from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone

import pytest
from lib.disclosures.candidate_extraction import SemanticClaimCandidate
from lib.disclosures.faithfulness import (
    DETERMINISTIC_FAITHFULNESS_VERSION,
    FaithfulnessCheckMethod,
    FaithfulnessDimension,
    FaithfulnessDimensionOutcome,
    FaithfulnessDimensionResult,
    FaithfulnessReasonCode,
    FaithfulnessSchemaError,
    FaithfulnessVerificationResult,
    FaithfulnessVerificationStatus,
    compute_candidate_reference,
    verify_candidate_deterministically,
)
from lib.disclosures.normalization import NormalizedDisclosureDocument, normalize_edinet_type1_zip
from lib.disclosures.semantic_claims import ClaimDirection, EvidenceSpan, FaithfulnessOutcome, SemanticClaimType
from lib.evidence.model import AiDerivedProvenance

_XHTML_OPEN = '<html xmlns="http://www.w3.org/1999/xhtml" xmlns:ix="http://www.xbrl.org/2008/inlineXBRL">'
_VERIFIED_AT = datetime(2026, 1, 1, tzinfo=UTC)


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


def _fake_provenance() -> AiDerivedProvenance:
    return AiDerivedProvenance(
        model_provider="test-provider", model_name="test-model", model_version="v1", generated_at=datetime(2026, 1, 1, tzinfo=UTC)
    )


def _candidate(
    *,
    evidence_span: EvidenceSpan,
    claim_type: SemanticClaimType = SemanticClaimType.PERFORMANCE_CHANGE,
    text: str,
    direction: ClaimDirection = ClaimDirection.UNSPECIFIED,
) -> SemanticClaimCandidate:
    return SemanticClaimCandidate(
        claim_type=claim_type,
        normalized_claim_text=text,
        direction=direction,
        evidence_span=evidence_span,
        extraction_version="EXTRACT_V1",
        extraction_provenance=_fake_provenance(),
    )


def _doc_and_span(
    body_inner: str, *, taxonomy_name: str = "jpcrp_cor:ManagementAnalysisTextBlock"
) -> tuple[NormalizedDisclosureDocument, EvidenceSpan]:
    doc = _single_member_doc(_ix(taxonomy_name, body_inner))
    return doc, _span_for(doc)


_BUSINESS_RISK_TAXONOMY = "jpcrp_cor:BusinessRisksTextBlock"


def _dim_result(result: FaithfulnessVerificationResult, dimension: FaithfulnessDimension) -> FaithfulnessDimensionResult:
    by_dim = {r.dimension: r for r in result.dimension_results}
    return by_dim[dimension]


# ============================================================
# 1. Gates
# ============================================================


def test_01_stale_evidence_span_blocks_verification() -> None:
    doc, span = _doc_and_span("本文です。")
    stale_span = replace(span, source_normalizer_version="STALE_VERSION_DOES_NOT_MATCH")
    candidate = _candidate(evidence_span=stale_span, text="本文です。")

    result = verify_candidate_deterministically(candidate=candidate, document=doc, verified_at=_VERIFIED_AT)

    assert result.status == FaithfulnessVerificationStatus.SOURCE_REVALIDATION_FAILED
    assert result.overall_outcome is None
    assert result.dimension_results == ()


def test_candidate_integrity_gate_rejects_non_candidate_object() -> None:
    doc, _span = _doc_and_span("本文です。")

    result = verify_candidate_deterministically(candidate={"not": "a candidate"}, document=doc, verified_at=_VERIFIED_AT)

    assert result.status == FaithfulnessVerificationStatus.CANDIDATE_INTEGRITY_FAILED
    assert result.overall_outcome is None
    assert result.candidate_reference == ""


# ============================================================
# 2. Exact match does not bypass claim_type requirement
# ============================================================


def test_02_exact_quote_non_eligible_claim_type_stays_review_required() -> None:
    text = "売上高は堅調に推移した。"
    doc, span = _doc_and_span(text)
    candidate = _candidate(evidence_span=span, claim_type=SemanticClaimType.PERFORMANCE_CHANGE, text=text)

    result = verify_candidate_deterministically(candidate=candidate, document=doc, verified_at=_VERIFIED_AT)

    assert result.status == FaithfulnessVerificationStatus.SUCCESS
    assert result.overall_outcome == FaithfulnessOutcome.REVIEW_REQUIRED
    prop = _dim_result(result, FaithfulnessDimension.PROPOSITION_IDENTITY)
    assert prop.outcome == FaithfulnessDimensionOutcome.AMBIGUOUS
    assert prop.reason_code == FaithfulnessReasonCode.SEMANTIC_VERIFICATION_REQUIRED


def test_23_exact_quote_with_wrong_direction_still_rejects() -> None:
    text = "リスクは増加した。"
    doc, span = _doc_and_span(text, taxonomy_name=_BUSINESS_RISK_TAXONOMY)
    candidate = _candidate(
        evidence_span=span, claim_type=SemanticClaimType.BUSINESS_RISK, text=text, direction=ClaimDirection.DECREASE
    )

    result = verify_candidate_deterministically(candidate=candidate, document=doc, verified_at=_VERIFIED_AT)

    assert result.overall_outcome == FaithfulnessOutcome.REJECT
    prop = _dim_result(result, FaithfulnessDimension.PROPOSITION_IDENTITY)
    assert prop.outcome == FaithfulnessDimensionOutcome.FAIL
    assert prop.reason_code == FaithfulnessReasonCode.DIRECTION_MISMATCH_DETECTED


# ============================================================
# 3/4. Direction consistency
# ============================================================


def test_03_increase_source_with_decrease_direction_rejects() -> None:
    text = "リスクは増加した。"
    doc, span = _doc_and_span(text, taxonomy_name=_BUSINESS_RISK_TAXONOMY)
    candidate = _candidate(
        evidence_span=span, claim_type=SemanticClaimType.BUSINESS_RISK, text=text, direction=ClaimDirection.DECREASE
    )

    result = verify_candidate_deterministically(candidate=candidate, document=doc, verified_at=_VERIFIED_AT)

    assert result.overall_outcome == FaithfulnessOutcome.REJECT


def test_04_decrease_source_with_increase_direction_rejects() -> None:
    text = "リスクは減少した。"
    doc, span = _doc_and_span(text, taxonomy_name=_BUSINESS_RISK_TAXONOMY)
    candidate = _candidate(
        evidence_span=span, claim_type=SemanticClaimType.BUSINESS_RISK, text=text, direction=ClaimDirection.INCREASE
    )

    result = verify_candidate_deterministically(candidate=candidate, document=doc, verified_at=_VERIFIED_AT)

    assert result.overall_outcome == FaithfulnessOutcome.REJECT
    prop = _dim_result(result, FaithfulnessDimension.PROPOSITION_IDENTITY)
    assert prop.reason_code == FaithfulnessReasonCode.DIRECTION_MISMATCH_DETECTED


def test_05_explicit_movement_with_unspecified_direction_reviews() -> None:
    text = "リスクは増加した。"
    doc, span = _doc_and_span(text, taxonomy_name=_BUSINESS_RISK_TAXONOMY)
    candidate = _candidate(
        evidence_span=span, claim_type=SemanticClaimType.BUSINESS_RISK, text=text, direction=ClaimDirection.UNSPECIFIED
    )

    result = verify_candidate_deterministically(candidate=candidate, document=doc, verified_at=_VERIFIED_AT)

    assert result.overall_outcome == FaithfulnessOutcome.REVIEW_REQUIRED
    prop = _dim_result(result, FaithfulnessDimension.PROPOSITION_IDENTITY)
    assert prop.outcome == FaithfulnessDimensionOutcome.AMBIGUOUS
    assert prop.reason_code == FaithfulnessReasonCode.DIRECTION_UNSPECIFIED_WITH_EXPLICIT_SOURCE


def test_06_candidate_direction_without_source_marker_reviews() -> None:
    text = "リスクについて記載する。"
    doc, span = _doc_and_span(text, taxonomy_name=_BUSINESS_RISK_TAXONOMY)
    candidate = _candidate(
        evidence_span=span, claim_type=SemanticClaimType.BUSINESS_RISK, text=text, direction=ClaimDirection.INCREASE
    )

    result = verify_candidate_deterministically(candidate=candidate, document=doc, verified_at=_VERIFIED_AT)

    assert result.overall_outcome == FaithfulnessOutcome.REVIEW_REQUIRED
    prop = _dim_result(result, FaithfulnessDimension.PROPOSITION_IDENTITY)
    assert prop.outcome == FaithfulnessDimensionOutcome.AMBIGUOUS
    assert prop.reason_code == FaithfulnessReasonCode.DIRECTION_REQUIRES_SEMANTIC_REVIEW


def test_improvement_word_alone_does_not_imply_increase() -> None:
    text = "業績は改善した。"
    doc, span = _doc_and_span(text, taxonomy_name=_BUSINESS_RISK_TAXONOMY)
    candidate = _candidate(
        evidence_span=span, claim_type=SemanticClaimType.BUSINESS_RISK, text=text, direction=ClaimDirection.INCREASE
    )

    result = verify_candidate_deterministically(candidate=candidate, document=doc, verified_at=_VERIFIED_AT)

    # "改善"はMarker語彙に含まれないため evidence_marker=None、
    # candidate.direction=INCREASE のため DIRECTION_REQUIRES_SEMANTIC_REVIEW
    # (Silent PASSしない)。
    prop = _dim_result(result, FaithfulnessDimension.PROPOSITION_IDENTITY)
    assert prop.outcome == FaithfulnessDimensionOutcome.AMBIGUOUS
    assert prop.reason_code == FaithfulnessReasonCode.DIRECTION_REQUIRES_SEMANTIC_REVIEW


# ============================================================
# 7-10. Quantity
# ============================================================


def test_07_invented_quantity_rejects() -> None:
    doc, span = _doc_and_span("業績は堅調に推移した。")
    candidate = _candidate(evidence_span=span, text="業績は4.0%増加した。")

    result = verify_candidate_deterministically(candidate=candidate, document=doc, verified_at=_VERIFIED_AT)

    assert result.overall_outcome == FaithfulnessOutcome.REJECT
    quantity = _dim_result(result, FaithfulnessDimension.QUANTITY)
    assert quantity.outcome == FaithfulnessDimensionOutcome.FAIL
    assert quantity.reason_code == FaithfulnessReasonCode.QUANTITY_INVENTED


def test_08_quantity_value_mismatch_rejects() -> None:
    doc, span = _doc_and_span("売上高は4.0%増加した。")
    candidate = _candidate(evidence_span=span, text="売上高は14.0%増加した。")

    result = verify_candidate_deterministically(candidate=candidate, document=doc, verified_at=_VERIFIED_AT)

    assert result.overall_outcome == FaithfulnessOutcome.REJECT
    quantity = _dim_result(result, FaithfulnessDimension.QUANTITY)
    assert quantity.reason_code == FaithfulnessReasonCode.QUANTITY_VALUE_MISMATCH


def test_09_quantity_unit_mismatch_rejects() -> None:
    # 同じ数値(500)だが単位Tokenが異なる(台 vs 円)——スケールKanjiを
    # 挟まないことで「同じ生の数値、異なる単位」というUNIT_MISMATCHを
    # 明確に切り分ける(950億円 vs 950%のような桁が全く異なるCaseは
    # QUANTITY_INVENTEDが正しい、別Testで確認済み)。
    doc, span = _doc_and_span("販売台数は500台増加した。")
    candidate = _candidate(evidence_span=span, text="販売台数は500円増加した。")

    result = verify_candidate_deterministically(candidate=candidate, document=doc, verified_at=_VERIFIED_AT)

    assert result.overall_outcome == FaithfulnessOutcome.REJECT
    quantity = _dim_result(result, FaithfulnessDimension.QUANTITY)
    assert quantity.reason_code == FaithfulnessReasonCode.QUANTITY_UNIT_MISMATCH


def test_quantity_different_magnitude_and_unit_is_invented_not_unit_mismatch() -> None:
    doc, span = _doc_and_span("利益は950億円増加した。")
    candidate = _candidate(evidence_span=span, text="利益は950%増加した。")

    result = verify_candidate_deterministically(candidate=candidate, document=doc, verified_at=_VERIFIED_AT)

    assert result.overall_outcome == FaithfulnessOutcome.REJECT
    quantity = _dim_result(result, FaithfulnessDimension.QUANTITY)
    assert quantity.reason_code == FaithfulnessReasonCode.QUANTITY_INVENTED


def test_quantity_sign_mismatch_rejects() -> None:
    doc, span = _doc_and_span("利益は△950億円となった。")
    candidate = _candidate(evidence_span=span, text="利益は950億円となった。")

    result = verify_candidate_deterministically(candidate=candidate, document=doc, verified_at=_VERIFIED_AT)

    assert result.overall_outcome == FaithfulnessOutcome.REJECT
    quantity = _dim_result(result, FaithfulnessDimension.QUANTITY)
    assert quantity.reason_code == FaithfulnessReasonCode.QUANTITY_SIGN_MISMATCH


def test_10_matching_quantity_has_no_quantity_failure() -> None:
    text = "利益は4.0%増加した。"
    doc, span = _doc_and_span(text)
    candidate = _candidate(evidence_span=span, text=text)

    result = verify_candidate_deterministically(candidate=candidate, document=doc, verified_at=_VERIFIED_AT)

    quantity = _dim_result(result, FaithfulnessDimension.QUANTITY)
    assert quantity.outcome == FaithfulnessDimensionOutcome.PASS


def test_quantity_large_scale_kanji_parses_correctly() -> None:
    text = "売上高は2兆4,642億円となった。"
    doc, span = _doc_and_span(text)
    candidate = _candidate(evidence_span=span, text=text)

    result = verify_candidate_deterministically(candidate=candidate, document=doc, verified_at=_VERIFIED_AT)

    quantity = _dim_result(result, FaithfulnessDimension.QUANTITY)
    assert quantity.outcome == FaithfulnessDimensionOutcome.PASS


def test_quantity_neither_side_has_quantity_is_not_applicable() -> None:
    text = "業績は堅調に推移した。"
    doc, span = _doc_and_span(text, taxonomy_name=_BUSINESS_RISK_TAXONOMY)
    candidate = _candidate(evidence_span=span, claim_type=SemanticClaimType.BUSINESS_RISK, text=text)

    result = verify_candidate_deterministically(candidate=candidate, document=doc, verified_at=_VERIFIED_AT)

    quantity = _dim_result(result, FaithfulnessDimension.QUANTITY)
    assert quantity.outcome == FaithfulnessDimensionOutcome.NOT_APPLICABLE


def test_quantity_required_by_claim_type_forces_ambiguous_not_not_applicable() -> None:
    text = "業績は堅調に推移した。"
    doc, span = _doc_and_span(text)
    candidate = _candidate(evidence_span=span, claim_type=SemanticClaimType.PERFORMANCE_CHANGE, text=text)

    result = verify_candidate_deterministically(candidate=candidate, document=doc, verified_at=_VERIFIED_AT)

    quantity = _dim_result(result, FaithfulnessDimension.QUANTITY)
    assert quantity.outcome == FaithfulnessDimensionOutcome.AMBIGUOUS
    assert quantity.reason_code == FaithfulnessReasonCode.SEMANTIC_VERIFICATION_REQUIRED


# ============================================================
# 11/12. Negation
# ============================================================


def test_11_clear_negation_inversion_rejects() -> None:
    doc, span = _doc_and_span("重要な変更はありません。", taxonomy_name=_BUSINESS_RISK_TAXONOMY)
    candidate = _candidate(evidence_span=span, claim_type=SemanticClaimType.BUSINESS_RISK, text="重要な変更があった。")

    result = verify_candidate_deterministically(candidate=candidate, document=doc, verified_at=_VERIFIED_AT)

    assert result.overall_outcome == FaithfulnessOutcome.REJECT
    negation = _dim_result(result, FaithfulnessDimension.NEGATION)
    assert negation.outcome == FaithfulnessDimensionOutcome.FAIL
    assert negation.reason_code == FaithfulnessReasonCode.NEGATION_INVERTED


def test_12_double_negation_is_ambiguous_and_reviews() -> None:
    text = "問題がないわけではない。"
    doc, span = _doc_and_span(text)
    candidate = _candidate(evidence_span=span, claim_type=SemanticClaimType.PERFORMANCE_DRIVER, text=text)

    result = verify_candidate_deterministically(candidate=candidate, document=doc, verified_at=_VERIFIED_AT)

    negation = _dim_result(result, FaithfulnessDimension.NEGATION)
    assert negation.outcome == FaithfulnessDimensionOutcome.AMBIGUOUS
    assert negation.reason_code == FaithfulnessReasonCode.NEGATION_AMBIGUOUS
    assert result.overall_outcome == FaithfulnessOutcome.REVIEW_REQUIRED


def test_negation_neither_side_negated_passes() -> None:
    text = "業績は堅調に推移した。"
    doc, span = _doc_and_span(text, taxonomy_name=_BUSINESS_RISK_TAXONOMY)
    candidate = _candidate(evidence_span=span, claim_type=SemanticClaimType.BUSINESS_RISK, text=text)

    result = verify_candidate_deterministically(candidate=candidate, document=doc, verified_at=_VERIFIED_AT)

    negation = _dim_result(result, FaithfulnessDimension.NEGATION)
    assert negation.outcome == FaithfulnessDimensionOutcome.PASS


def test_negation_never_not_applicable_by_construction() -> None:
    with pytest.raises(FaithfulnessSchemaError):
        FaithfulnessDimensionResult(
            dimension=FaithfulnessDimension.NEGATION,
            outcome=FaithfulnessDimensionOutcome.NOT_APPLICABLE,
            reason_code=FaithfulnessReasonCode.NOT_APPLICABLE_NO_RELEVANT_CONTENT,
            checked_by=FaithfulnessCheckMethod.DETERMINISTIC,
        )


# ============================================================
# 13. Causal strength
# ============================================================


def test_13_causal_tier_upgrade_rejects() -> None:
    doc, span = _doc_and_span("為替影響は一因である。")
    candidate = _candidate(
        evidence_span=span, claim_type=SemanticClaimType.PERFORMANCE_DRIVER, text="為替影響は唯一の原因である。"
    )

    result = verify_candidate_deterministically(candidate=candidate, document=doc, verified_at=_VERIFIED_AT)

    assert result.overall_outcome == FaithfulnessOutcome.REJECT
    causal = _dim_result(result, FaithfulnessDimension.CAUSAL_STRENGTH)
    assert causal.outcome == FaithfulnessDimensionOutcome.FAIL
    assert causal.reason_code == FaithfulnessReasonCode.CAUSAL_TIER_UPGRADED
    assert causal.checked_by == FaithfulnessCheckMethod.DETERMINISTIC


def test_causal_strength_required_by_claim_type_forces_ambiguous() -> None:
    text = "業績は堅調に推移した。"
    doc, span = _doc_and_span(text)
    candidate = _candidate(evidence_span=span, claim_type=SemanticClaimType.PERFORMANCE_DRIVER, text=text)

    result = verify_candidate_deterministically(candidate=candidate, document=doc, verified_at=_VERIFIED_AT)

    causal = _dim_result(result, FaithfulnessDimension.CAUSAL_STRENGTH)
    assert causal.outcome == FaithfulnessDimensionOutcome.AMBIGUOUS
    assert causal.reason_code == FaithfulnessReasonCode.CAUSAL_REQUIRES_SEMANTIC_REVIEW


# ============================================================
# 14. Certainty / commitment
# ============================================================


def test_14_certainty_upgrade_rejects() -> None:
    doc, span = _doc_and_span("損失が発生する可能性がある。", taxonomy_name=_BUSINESS_RISK_TAXONOMY)
    candidate = _candidate(evidence_span=span, claim_type=SemanticClaimType.BUSINESS_RISK, text="損失が発生する。")

    result = verify_candidate_deterministically(candidate=candidate, document=doc, verified_at=_VERIFIED_AT)

    assert result.overall_outcome == FaithfulnessOutcome.REJECT
    certainty = _dim_result(result, FaithfulnessDimension.CERTAINTY_AND_COMMITMENT)
    assert certainty.outcome == FaithfulnessDimensionOutcome.FAIL
    assert certainty.reason_code == FaithfulnessReasonCode.CERTAINTY_TIER_UPGRADED


def test_commitment_tier_upgrade_rejects() -> None:
    doc, span = _doc_and_span("設備投資を検討している。", taxonomy_name=_BUSINESS_RISK_TAXONOMY)
    candidate = _candidate(evidence_span=span, claim_type=SemanticClaimType.BUSINESS_RISK, text="設備投資を実施している。")

    result = verify_candidate_deterministically(candidate=candidate, document=doc, verified_at=_VERIFIED_AT)

    assert result.overall_outcome == FaithfulnessOutcome.REJECT
    certainty = _dim_result(result, FaithfulnessDimension.CERTAINTY_AND_COMMITMENT)
    assert certainty.reason_code == FaithfulnessReasonCode.COMMITMENT_TIER_UPGRADED


# ============================================================
# 15. Temporal scope
# ============================================================


def test_15_historical_to_future_category_jump_rejects() -> None:
    doc, span = _doc_and_span("当中間連結会計期間の業績は堅調であった。", taxonomy_name=_BUSINESS_RISK_TAXONOMY)
    candidate = _candidate(evidence_span=span, claim_type=SemanticClaimType.OUTLOOK, text="今後も継続的に堅調である。")

    result = verify_candidate_deterministically(candidate=candidate, document=doc, verified_at=_VERIFIED_AT)

    assert result.overall_outcome == FaithfulnessOutcome.REJECT
    temporal = _dim_result(result, FaithfulnessDimension.TEMPORAL_SCOPE)
    assert temporal.outcome == FaithfulnessDimensionOutcome.FAIL
    assert temporal.reason_code == FaithfulnessReasonCode.TEMPORAL_CATEGORY_MISMATCH


def test_temporal_scope_required_by_claim_type_forces_ambiguous() -> None:
    text = "業績は堅調に推移した。"
    doc, span = _doc_and_span(text)
    candidate = _candidate(evidence_span=span, claim_type=SemanticClaimType.PERFORMANCE_CHANGE, text=text)

    result = verify_candidate_deterministically(candidate=candidate, document=doc, verified_at=_VERIFIED_AT)

    temporal = _dim_result(result, FaithfulnessDimension.TEMPORAL_SCOPE)
    assert temporal.outcome == FaithfulnessDimensionOutcome.AMBIGUOUS
    assert temporal.reason_code == FaithfulnessReasonCode.TEMPORAL_REQUIRES_SEMANTIC_REVIEW


# ============================================================
# 16. Paraphrase requiring semantic verification
# ============================================================


def test_16_paraphrase_requires_semantic_verification_reviews() -> None:
    doc, span = _doc_and_span("海外事業の販売が拡大した。")
    candidate = _candidate(evidence_span=span, claim_type=SemanticClaimType.PERFORMANCE_CHANGE, text="海外事業の販売が伸びた。")

    result = verify_candidate_deterministically(candidate=candidate, document=doc, verified_at=_VERIFIED_AT)

    assert result.overall_outcome == FaithfulnessOutcome.REVIEW_REQUIRED
    assert result.status == FaithfulnessVerificationStatus.SUCCESS


def test_subject_attribution_paraphrase_is_ambiguous_not_accept() -> None:
    doc, span = _doc_and_span("金融事業の利益は増加した。")
    candidate = _candidate(evidence_span=span, claim_type=SemanticClaimType.PERFORMANCE_CHANGE, text="金融部門の収益は伸びた。")

    result = verify_candidate_deterministically(candidate=candidate, document=doc, verified_at=_VERIFIED_AT)

    subject = _dim_result(result, FaithfulnessDimension.SUBJECT_ATTRIBUTION)
    assert subject.outcome == FaithfulnessDimensionOutcome.AMBIGUOUS
    assert subject.reason_code == FaithfulnessReasonCode.SEMANTIC_VERIFICATION_REQUIRED


# ============================================================
# 17. Deterministic hard fail cannot be converted to REVIEW
# ============================================================


def test_17_deterministic_hard_fail_overrides_ambiguous_review() -> None:
    doc, span = _doc_and_span("業績は堅調に推移した。")
    # PROPOSITION_IDENTITY(eligibility)はAMBIGUOUS、QUANTITYはHard-Fail
    # (捏造数値)——両方存在してもOverallはREJECT(REVIEWへ緩和されない)。
    candidate = _candidate(
        evidence_span=span,
        claim_type=SemanticClaimType.PERFORMANCE_CHANGE,
        text="業績は4.0%増加した。",
        direction=ClaimDirection.INCREASE,
    )

    result = verify_candidate_deterministically(candidate=candidate, document=doc, verified_at=_VERIFIED_AT)

    prop = _dim_result(result, FaithfulnessDimension.PROPOSITION_IDENTITY)
    quantity = _dim_result(result, FaithfulnessDimension.QUANTITY)
    assert prop.outcome == FaithfulnessDimensionOutcome.AMBIGUOUS
    assert quantity.outcome == FaithfulnessDimensionOutcome.FAIL
    assert result.overall_outcome == FaithfulnessOutcome.REJECT


# ============================================================
# 18-21. FaithfulnessVerificationResult invariants
# ============================================================


def test_18_naive_verified_at_rejected() -> None:
    with pytest.raises(FaithfulnessSchemaError):
        FaithfulnessVerificationResult(
            status=FaithfulnessVerificationStatus.SUCCESS,
            overall_outcome=FaithfulnessOutcome.ACCEPT,
            candidate_reference="CANDREF_x",
            verification_version=DETERMINISTIC_FAITHFULNESS_VERSION,
            verified_at=datetime(2026, 1, 1),  # naive
        )


def test_19_non_utc_aware_verified_at_rejected() -> None:
    jst = timezone(timedelta(hours=9))
    with pytest.raises(FaithfulnessSchemaError):
        FaithfulnessVerificationResult(
            status=FaithfulnessVerificationStatus.SUCCESS,
            overall_outcome=FaithfulnessOutcome.ACCEPT,
            candidate_reference="CANDREF_x",
            verification_version=DETERMINISTIC_FAITHFULNESS_VERSION,
            verified_at=datetime(2026, 1, 1, tzinfo=jst),
        )


def test_20_deterministic_success_has_no_verification_provenance() -> None:
    text = "業績は堅調に推移した。"
    doc, span = _doc_and_span(text)
    candidate = _candidate(evidence_span=span, text=text)

    result = verify_candidate_deterministically(candidate=candidate, document=doc, verified_at=_VERIFIED_AT)

    assert result.status == FaithfulnessVerificationStatus.SUCCESS
    assert result.verification_provenance is None
    assert result.verification_version == DETERMINISTIC_FAITHFULNESS_VERSION


def test_21a_success_status_requires_non_none_outcome() -> None:
    with pytest.raises(FaithfulnessSchemaError):
        FaithfulnessVerificationResult(
            status=FaithfulnessVerificationStatus.SUCCESS,
            overall_outcome=None,
            candidate_reference="CANDREF_x",
            verification_version=DETERMINISTIC_FAITHFULNESS_VERSION,
            verified_at=_VERIFIED_AT,
        )


def test_21b_non_success_status_requires_none_outcome() -> None:
    with pytest.raises(FaithfulnessSchemaError):
        FaithfulnessVerificationResult(
            status=FaithfulnessVerificationStatus.SOURCE_REVALIDATION_FAILED,
            overall_outcome=FaithfulnessOutcome.ACCEPT,
            candidate_reference="CANDREF_x",
            verification_version=DETERMINISTIC_FAITHFULNESS_VERSION,
            verified_at=_VERIFIED_AT,
        )


def test_verification_provenance_set_without_model_check_rejected() -> None:
    with pytest.raises(FaithfulnessSchemaError):
        FaithfulnessVerificationResult(
            status=FaithfulnessVerificationStatus.SUCCESS,
            overall_outcome=FaithfulnessOutcome.ACCEPT,
            dimension_results=(
                FaithfulnessDimensionResult(
                    dimension=FaithfulnessDimension.NEGATION,
                    outcome=FaithfulnessDimensionOutcome.PASS,
                    reason_code=FaithfulnessReasonCode.NO_ISSUE_DETECTED,
                    checked_by=FaithfulnessCheckMethod.DETERMINISTIC,
                ),
            ),
            candidate_reference="CANDREF_x",
            verification_version=DETERMINISTIC_FAITHFULNESS_VERSION,
            verified_at=_VERIFIED_AT,
            verification_provenance=_fake_provenance(),
        )


# ============================================================
# 22. NOT_APPLICABLE forbidden on required dimension
# ============================================================


def test_22_required_dimension_never_reports_not_applicable() -> None:
    text = "業績は堅調に推移した。"
    doc, span = _doc_and_span(text, taxonomy_name=_BUSINESS_RISK_TAXONOMY)
    candidate = _candidate(evidence_span=span, claim_type=SemanticClaimType.BUSINESS_RISK, text=text)

    result = verify_candidate_deterministically(candidate=candidate, document=doc, verified_at=_VERIFIED_AT)

    # BUSINESS_RISKはCERTAINTY_AND_COMMITMENT/NEGATIONを必須とする
    # (D0102.4 §25)。CERTAINTY_AND_COMMITMENTはMarker不在ならNOT_APPLICABLEに
    # なりうる軸だが、必須Overrideにより NOT_APPLICABLE は現れない。
    certainty = _dim_result(result, FaithfulnessDimension.CERTAINTY_AND_COMMITMENT)
    assert certainty.outcome != FaithfulnessDimensionOutcome.NOT_APPLICABLE


def test_proposition_identity_never_not_applicable_by_construction() -> None:
    with pytest.raises(FaithfulnessSchemaError):
        FaithfulnessDimensionResult(
            dimension=FaithfulnessDimension.PROPOSITION_IDENTITY,
            outcome=FaithfulnessDimensionOutcome.NOT_APPLICABLE,
            reason_code=FaithfulnessReasonCode.NOT_APPLICABLE_NO_RELEVANT_CONTENT,
            checked_by=FaithfulnessCheckMethod.DETERMINISTIC,
        )


def test_subject_attribution_never_not_applicable_by_construction() -> None:
    with pytest.raises(FaithfulnessSchemaError):
        FaithfulnessDimensionResult(
            dimension=FaithfulnessDimension.SUBJECT_ATTRIBUTION,
            outcome=FaithfulnessDimensionOutcome.NOT_APPLICABLE,
            reason_code=FaithfulnessReasonCode.NOT_APPLICABLE_NO_RELEVANT_CONTENT,
            checked_by=FaithfulnessCheckMethod.DETERMINISTIC,
        )


# ============================================================
# 24. BUSINESS_RISK taxonomy eligibility
# ============================================================


def test_24_business_risk_wrong_taxonomy_cannot_accept() -> None:
    text = "業績は堅調に推移した。"
    doc, span = _doc_and_span(text, taxonomy_name="jpcrp_cor:ManagementAnalysisTextBlock")
    candidate = _candidate(evidence_span=span, claim_type=SemanticClaimType.BUSINESS_RISK, text=text)

    result = verify_candidate_deterministically(candidate=candidate, document=doc, verified_at=_VERIFIED_AT)

    assert result.overall_outcome == FaithfulnessOutcome.REJECT
    prop = _dim_result(result, FaithfulnessDimension.PROPOSITION_IDENTITY)
    assert prop.reason_code == FaithfulnessReasonCode.BUSINESS_RISK_TAXONOMY_INELIGIBLE


# ============================================================
# Positive case: everything consistent reaches ACCEPT
# ============================================================


def test_fully_consistent_business_risk_candidate_accepts() -> None:
    text = "為替の影響により、利益が減少する可能性がある。"
    doc, span = _doc_and_span(text, taxonomy_name=_BUSINESS_RISK_TAXONOMY)
    candidate = _candidate(
        evidence_span=span, claim_type=SemanticClaimType.BUSINESS_RISK, text=text, direction=ClaimDirection.DECREASE
    )

    result = verify_candidate_deterministically(candidate=candidate, document=doc, verified_at=_VERIFIED_AT)

    assert result.status == FaithfulnessVerificationStatus.SUCCESS
    assert result.overall_outcome == FaithfulnessOutcome.ACCEPT
    for dim_result in result.dimension_results:
        assert dim_result.outcome in (FaithfulnessDimensionOutcome.PASS, FaithfulnessDimensionOutcome.NOT_APPLICABLE)


# ============================================================
# candidate_reference
# ============================================================


def test_candidate_reference_is_deterministic_and_not_identity_key() -> None:
    text = "業績は堅調に推移した。"
    doc, span = _doc_and_span(text)
    candidate_a = _candidate(evidence_span=span, text=text)
    candidate_b = _candidate(evidence_span=span, text=text)
    candidate_different_direction = _candidate(evidence_span=span, text=text, direction=ClaimDirection.INCREASE)

    ref_a = compute_candidate_reference(candidate_a)
    ref_b = compute_candidate_reference(candidate_b)
    ref_c = compute_candidate_reference(candidate_different_direction)

    assert ref_a == ref_b
    assert ref_a != ref_c
    assert ref_a.startswith("CANDREF_")
    assert not hasattr(candidate_a, "claim_id")
    assert not hasattr(candidate_a, "semantic_identity_key")


def test_verified_at_never_used_as_pit_availability_field_name() -> None:
    """D0102.4A: VERIFICATION_TIMESTAMP_IS_NOT_PIT_AVAILABILITY = TRUE。
    `FaithfulnessVerificationResult`にPIT可用性相当のField名
    (market_public_at/provider_available_at/available_at)が存在しない
    ことを構造的に確認する。"""
    field_names = set(FaithfulnessVerificationResult.__dataclass_fields__.keys())
    assert "market_public_at" not in field_names
    assert "provider_available_at" not in field_names
    assert "available_at" not in field_names
    assert "verified_at" in field_names


# ============================================================
# D0102.4.1.1 — Codex Adversarial Audit Closure(F01-F06)
#
# 各TestはPublic Entrypoint(`verify_candidate_deterministically()`、
# F06のみSchema Constructor直接)を通じてFindingを再現・修正確認する。
# ============================================================


def test_f01_overlapping_negation_markers_no_longer_double_counted() -> None:
    """F01: `変更はない`/`認められない`は`ない`のSuperstringであり、旧
    実装は`str.count()`合算でこれらを2重Countしていた(実際には1件の
    否定表現しかないTextがCount=2となりNEGATION_AMBIGUOUSへ誤って
    倒れていた)。同一極性(共に否定)のEvidence/Candidateであれば
    PASSすることを確認する。"""
    text = "重要な変更はない。"
    doc, span = _doc_and_span(text, taxonomy_name=_BUSINESS_RISK_TAXONOMY)
    candidate = _candidate(evidence_span=span, claim_type=SemanticClaimType.BUSINESS_RISK, text=text)

    result = verify_candidate_deterministically(candidate=candidate, document=doc, verified_at=_VERIFIED_AT)

    negation = _dim_result(result, FaithfulnessDimension.NEGATION)
    assert negation.outcome == FaithfulnessDimensionOutcome.PASS
    assert negation.reason_code == FaithfulnessReasonCode.NO_ISSUE_DETECTED


def test_f01_overlapping_negation_marker_ninth_word_also_fixed() -> None:
    text = "重要な事項は認められない。"
    doc, span = _doc_and_span(text, taxonomy_name=_BUSINESS_RISK_TAXONOMY)
    candidate = _candidate(evidence_span=span, claim_type=SemanticClaimType.BUSINESS_RISK, text=text)

    result = verify_candidate_deterministically(candidate=candidate, document=doc, verified_at=_VERIFIED_AT)

    negation = _dim_result(result, FaithfulnessDimension.NEGATION)
    assert negation.outcome == FaithfulnessDimensionOutcome.PASS


def test_f01_genuine_double_negation_still_ambiguous() -> None:
    # F01のFixが「Overlapping Markerの誤Count」のみを閉じ、真の二重否定
    # (2件の独立した否定表現)まで塞がないことを確認する回帰Test。
    text = "問題は認められないわけではない。"
    doc, span = _doc_and_span(text)
    candidate = _candidate(evidence_span=span, claim_type=SemanticClaimType.PERFORMANCE_DRIVER, text=text)

    result = verify_candidate_deterministically(candidate=candidate, document=doc, verified_at=_VERIFIED_AT)

    negation = _dim_result(result, FaithfulnessDimension.NEGATION)
    assert negation.outcome == FaithfulnessDimensionOutcome.AMBIGUOUS
    assert negation.reason_code == FaithfulnessReasonCode.NEGATION_AMBIGUOUS


def test_f02_ascii_minus_sign_is_parsed_not_silently_dropped() -> None:
    """F02: 旧実装は`△`のみを負号として認識しており、ASCII Minus(`-`)は
    Regexに無関係な文字として読み飛ばされ、`-950億円`から符号だけが
    静かに脱落して`950億円`(正)として誤抽出されていた。"""
    text = "利益は-950億円となった。"
    doc, span = _doc_and_span(text)
    candidate = _candidate(evidence_span=span, text=text)

    result = verify_candidate_deterministically(candidate=candidate, document=doc, verified_at=_VERIFIED_AT)

    quantity = _dim_result(result, FaithfulnessDimension.QUANTITY)
    assert quantity.outcome == FaithfulnessDimensionOutcome.PASS


def test_f02_ascii_minus_sign_mismatch_now_detected() -> None:
    """符号脱落Bugが直ったことの直接証拠: Evidence`-950億円`に対し、
    Candidateが符号を落とした`950億円`を主張した場合、旧実装では
    両者とも(誤って)+950億円へParseされ一致=PASSしていたが、修正後は
    QUANTITY_SIGN_MISMATCHでFAILする。"""
    doc, span = _doc_and_span("利益は-950億円となった。")
    candidate = _candidate(evidence_span=span, text="利益は950億円となった。")

    result = verify_candidate_deterministically(candidate=candidate, document=doc, verified_at=_VERIFIED_AT)

    assert result.overall_outcome == FaithfulnessOutcome.REJECT
    quantity = _dim_result(result, FaithfulnessDimension.QUANTITY)
    assert quantity.outcome == FaithfulnessDimensionOutcome.FAIL
    assert quantity.reason_code == FaithfulnessReasonCode.QUANTITY_SIGN_MISMATCH


def test_f02_fullwidth_minus_sign_also_recognized() -> None:
    doc, span = _doc_and_span("利益は－950億円となった。")
    candidate = _candidate(evidence_span=span, text="利益は950億円となった。")

    result = verify_candidate_deterministically(candidate=candidate, document=doc, verified_at=_VERIFIED_AT)

    quantity = _dim_result(result, FaithfulnessDimension.QUANTITY)
    assert quantity.reason_code == FaithfulnessReasonCode.QUANTITY_SIGN_MISMATCH


def test_f03_cross_proposition_quantity_borrowing_no_longer_passes() -> None:
    """F03: Evidenceが複数の異なる数量(売上高4.0%増加・営業利益12.0%
    減少)を含む場合、Candidateが無関係な12.0%を「売上高」の数値として
    無断Borrowしても、旧実装は値の存在だけを見てPASSしていた。"""
    doc, span = _doc_and_span("売上高は4.0%増加し、営業利益は12.0%減少した。")
    candidate = _candidate(evidence_span=span, text="売上高は12.0%増加した。")

    result = verify_candidate_deterministically(candidate=candidate, document=doc, verified_at=_VERIFIED_AT)

    quantity = _dim_result(result, FaithfulnessDimension.QUANTITY)
    assert quantity.outcome == FaithfulnessDimensionOutcome.AMBIGUOUS
    assert quantity.reason_code == FaithfulnessReasonCode.SEMANTIC_VERIFICATION_REQUIRED
    assert result.overall_outcome == FaithfulnessOutcome.REVIEW_REQUIRED


def test_f03_single_quantity_in_category_still_passes_confidently() -> None:
    # F03のFixが必要以上に保守化していないことの回帰Test:
    # Evidence中の該当Categoryの数量が1件のみであれば、一致は
    # 曖昧さなくPASSできる(既存test_10と同型だが、F03修正後の
    # 挙動として明示的に再確認する)。
    text = "利益は4.0%増加した。"
    doc, span = _doc_and_span(text)
    candidate = _candidate(evidence_span=span, text=text)

    result = verify_candidate_deterministically(candidate=candidate, document=doc, verified_at=_VERIFIED_AT)

    quantity = _dim_result(result, FaithfulnessDimension.QUANTITY)
    assert quantity.outcome == FaithfulnessDimensionOutcome.PASS


def test_f04_negated_increase_marker_no_longer_matches_increase_direction() -> None:
    """F04: `増加しなかった`(否定形)にも`増加`という部分文字列が含まれる
    ため、旧実装はEvidenceが増加を否定しているにもかかわらず
    `evidence_marker=INCREASE`と誤判定し、`candidate.direction=INCREASE`
    と(誤って)一致させていた。"""
    text = "売上高は増加しなかった。"
    doc, span = _doc_and_span(text, taxonomy_name=_BUSINESS_RISK_TAXONOMY)
    candidate = _candidate(
        evidence_span=span, claim_type=SemanticClaimType.BUSINESS_RISK, text=text, direction=ClaimDirection.INCREASE
    )

    result = verify_candidate_deterministically(candidate=candidate, document=doc, verified_at=_VERIFIED_AT)

    prop = _dim_result(result, FaithfulnessDimension.PROPOSITION_IDENTITY)
    assert prop.outcome == FaithfulnessDimensionOutcome.AMBIGUOUS
    assert prop.reason_code == FaithfulnessReasonCode.DIRECTION_REQUIRES_SEMANTIC_REVIEW


def test_f04_mixed_marker_occurrences_uses_the_unnegated_one() -> None:
    # 「否定形の出現もあるが、肯定形の出現も別途存在する」Mixed Caseでは
    # 肯定形の出現を正しく検出できることを確認する(F04修正が過剰に
    # 保守化していないことの回帰Test)。
    text = "前期は増加しなかったが、当期は増加した。"
    doc, span = _doc_and_span(text, taxonomy_name=_BUSINESS_RISK_TAXONOMY)
    candidate = _candidate(
        evidence_span=span, claim_type=SemanticClaimType.BUSINESS_RISK, text=text, direction=ClaimDirection.INCREASE
    )

    result = verify_candidate_deterministically(candidate=candidate, document=doc, verified_at=_VERIFIED_AT)

    prop = _dim_result(result, FaithfulnessDimension.PROPOSITION_IDENTITY)
    assert prop.outcome == FaithfulnessDimensionOutcome.PASS


def test_f05_multi_temporal_evidence_no_longer_falsely_rejects_future_candidate() -> None:
    """F05: Evidenceが実績報告(HISTORICAL)と先行き言及(FUTURE)を同一
    Text内に併記する一般的なPatternで、旧実装は最初に一致した
    Categoryのみを採用しHISTORICALへ収斂していたため、Evidence自身が
    支持しているFUTURE言及のCandidateまでMismatchでFAILしていた。"""
    doc, span = _doc_and_span(
        "当中間連結会計期間の実績を踏まえ、今後も同様の傾向が続く見通しである。", taxonomy_name=_BUSINESS_RISK_TAXONOMY
    )
    candidate = _candidate(evidence_span=span, claim_type=SemanticClaimType.OUTLOOK, text="今後も同様の傾向が続く見通しである。")

    result = verify_candidate_deterministically(candidate=candidate, document=doc, verified_at=_VERIFIED_AT)

    temporal = _dim_result(result, FaithfulnessDimension.TEMPORAL_SCOPE)
    assert temporal.outcome == FaithfulnessDimensionOutcome.PASS


def test_f05_genuinely_unsupported_future_claim_still_rejects() -> None:
    # F05のFixが必要以上に緩くなっていないことの回帰Test: Evidenceが
    # 純粋にHISTORICALのみでFUTURE言及が一切無い場合、Candidateの
    # FUTURE主張は引き続きMismatchでFAILする(既存test_15と同型)。
    doc, span = _doc_and_span("当中間連結会計期間の業績は堅調であった。", taxonomy_name=_BUSINESS_RISK_TAXONOMY)
    candidate = _candidate(evidence_span=span, claim_type=SemanticClaimType.OUTLOOK, text="今後も継続的に堅調である。")

    result = verify_candidate_deterministically(candidate=candidate, document=doc, verified_at=_VERIFIED_AT)

    temporal = _dim_result(result, FaithfulnessDimension.TEMPORAL_SCOPE)
    assert temporal.outcome == FaithfulnessDimensionOutcome.FAIL
    assert temporal.reason_code == FaithfulnessReasonCode.TEMPORAL_CATEGORY_MISMATCH


def _valid_dimension_result() -> FaithfulnessDimensionResult:
    return FaithfulnessDimensionResult(
        dimension=FaithfulnessDimension.NEGATION,
        outcome=FaithfulnessDimensionOutcome.PASS,
        reason_code=FaithfulnessReasonCode.NO_ISSUE_DETECTED,
        checked_by=FaithfulnessCheckMethod.DETERMINISTIC,
    )


def test_f06_dimension_results_must_be_a_tuple() -> None:
    with pytest.raises(FaithfulnessSchemaError):
        FaithfulnessVerificationResult(
            status=FaithfulnessVerificationStatus.SUCCESS,
            overall_outcome=FaithfulnessOutcome.ACCEPT,
            dimension_results=[_valid_dimension_result()],  # type: ignore[arg-type]
            candidate_reference="CANDREF_x",
            verification_version=DETERMINISTIC_FAITHFULNESS_VERSION,
            verified_at=_VERIFIED_AT,
        )


def test_f06_dimension_results_elements_must_be_dimension_result_type() -> None:
    with pytest.raises(FaithfulnessSchemaError):
        FaithfulnessVerificationResult(
            status=FaithfulnessVerificationStatus.SUCCESS,
            overall_outcome=FaithfulnessOutcome.ACCEPT,
            dimension_results=({"dimension": "NEGATION"},),  # type: ignore[arg-type]
            candidate_reference="CANDREF_x",
            verification_version=DETERMINISTIC_FAITHFULNESS_VERSION,
            verified_at=_VERIFIED_AT,
        )


def test_f06_duplicate_dimension_entries_rejected() -> None:
    with pytest.raises(FaithfulnessSchemaError):
        FaithfulnessVerificationResult(
            status=FaithfulnessVerificationStatus.SUCCESS,
            overall_outcome=FaithfulnessOutcome.ACCEPT,
            dimension_results=(_valid_dimension_result(), _valid_dimension_result()),
            candidate_reference="CANDREF_x",
            verification_version=DETERMINISTIC_FAITHFULNESS_VERSION,
            verified_at=_VERIFIED_AT,
        )


def test_f06_candidate_reference_must_be_str() -> None:
    with pytest.raises(FaithfulnessSchemaError):
        FaithfulnessVerificationResult(
            status=FaithfulnessVerificationStatus.SUCCESS,
            overall_outcome=FaithfulnessOutcome.ACCEPT,
            candidate_reference=12345,  # type: ignore[arg-type]
            verification_version=DETERMINISTIC_FAITHFULNESS_VERSION,
            verified_at=_VERIFIED_AT,
        )


def test_f06_verification_version_must_be_str() -> None:
    with pytest.raises(FaithfulnessSchemaError):
        FaithfulnessVerificationResult(
            status=FaithfulnessVerificationStatus.SUCCESS,
            overall_outcome=FaithfulnessOutcome.ACCEPT,
            candidate_reference="CANDREF_x",
            verification_version=12345,  # type: ignore[arg-type]
            verified_at=_VERIFIED_AT,
        )


def test_f06_verification_provenance_must_be_ai_derived_provenance_type() -> None:
    with pytest.raises(FaithfulnessSchemaError):
        FaithfulnessVerificationResult(
            status=FaithfulnessVerificationStatus.CANDIDATE_INTEGRITY_FAILED,
            overall_outcome=None,
            candidate_reference="",
            verification_version=DETERMINISTIC_FAITHFULNESS_VERSION,
            verified_at=_VERIFIED_AT,
            verification_provenance="not a real provenance",  # type: ignore[arg-type]
        )


def test_f06_reason_must_be_str_or_none() -> None:
    with pytest.raises(FaithfulnessSchemaError):
        FaithfulnessVerificationResult(
            status=FaithfulnessVerificationStatus.CANDIDATE_INTEGRITY_FAILED,
            overall_outcome=None,
            candidate_reference="",
            verification_version=DETERMINISTIC_FAITHFULNESS_VERSION,
            verified_at=_VERIFIED_AT,
            reason=12345,  # type: ignore[arg-type]
        )


def test_f06_valid_construction_with_dimension_results_still_succeeds() -> None:
    # F06のFixが正当なConstructionまで壊していないことの回帰Test。
    result = FaithfulnessVerificationResult(
        status=FaithfulnessVerificationStatus.SUCCESS,
        overall_outcome=FaithfulnessOutcome.ACCEPT,
        dimension_results=(_valid_dimension_result(),),
        candidate_reference="CANDREF_x",
        verification_version=DETERMINISTIC_FAITHFULNESS_VERSION,
        verified_at=_VERIFIED_AT,
    )
    assert result.status == FaithfulnessVerificationStatus.SUCCESS
