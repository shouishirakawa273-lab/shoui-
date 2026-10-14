"""`lib.disclosures.faithfulness`(Stage 3.18.6、D0102.4.1/D0102.4.2)の
Regression Test。

D0102.4/D0102.4A(DECISIONS.md、`READY_FOR_IMPLEMENTATION`)で承認された
Deterministic Core Architectureと、D0102.4.2で追加したModel-Assisted
Verification(`FaithfulnessVerifier` Protocol)+ACCEPT-only Promotion
Gateをそのまま検証する。**実LLM/Vendor SDKへの接続はこのModuleに一切
存在しない**(`MODEL_CALL_SITES = 0`、Model-Assisted部分は本Test内で
定義するDeterministic `FakeVerifier`のみで駆動する)。Fixture方式は
`test_candidate_extraction.py`と同じ(Synthetic EDINET-shaped ZIPを
構築し、実際の`normalize_edinet_type1_zip()`経由でD0101.1の実Objectを
得る)。
"""

from __future__ import annotations

import io
import zipfile
from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone

import pytest
from lib.disclosures.candidate_extraction import SemanticClaimCandidate

# D0102.4.2.1 D42-F02 Closure: `_determine_model_required_dimensions()`/
# `_run_all_dimension_checks()`はPublic APIでは無いが、「Deterministic
# FAILが確立した軸は絶対にModel-Requiredにならない」という内部不変条件
# 自体を直接検証するためにWhite-Box Testとしてimportする(Public
# Entrypointだけでは`FaithfulnessVerifierInput`にRequested Dimensionの
# 情報が含まれないため、この不変条件を外部から直接観測できない)。
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
    FaithfulnessVerifierInput,
    _determine_model_required_dimensions,
    _run_all_dimension_checks,
    compute_candidate_reference,
    promote_verified_candidate,
    verify_candidate_deterministically,
    verify_candidate_faithfulness,
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


def _full_accept_dimension_results() -> tuple[FaithfulnessDimensionResult, ...]:
    # D0102.4.2.1 D42-F01 Closure: status=SUCCESSのFaithfulnessVerification
    # Resultは全8軸を過不足無く含む必要がある(Completeness Invariant)。
    # 全軸PASS/NOT_APPLICABLE(NEVER_NOT_APPLICABLE 3軸のみPASS)なので
    # 正準Aggregationの結果は常にACCEPTになる。
    not_applicable_dims = (
        FaithfulnessDimension.CAUSAL_STRENGTH,
        FaithfulnessDimension.CERTAINTY_AND_COMMITMENT,
        FaithfulnessDimension.TEMPORAL_SCOPE,
        FaithfulnessDimension.QUANTITY,
    )
    results = []
    for dimension in FaithfulnessDimension:
        if dimension in not_applicable_dims:
            results.append(
                FaithfulnessDimensionResult(
                    dimension=dimension,
                    outcome=FaithfulnessDimensionOutcome.NOT_APPLICABLE,
                    reason_code=FaithfulnessReasonCode.NOT_APPLICABLE_NO_RELEVANT_CONTENT,
                    checked_by=FaithfulnessCheckMethod.DETERMINISTIC,
                )
            )
        else:
            results.append(
                FaithfulnessDimensionResult(
                    dimension=dimension,
                    outcome=FaithfulnessDimensionOutcome.PASS,
                    reason_code=FaithfulnessReasonCode.NO_ISSUE_DETECTED,
                    checked_by=FaithfulnessCheckMethod.DETERMINISTIC,
                )
            )
    return tuple(results)


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
    # F06のFixが正当なConstructionまで壊していないことの回帰Test
    # (D0102.4.2.1 D42-F01 ClosureのCompleteness/Aggregation Invariant
    # 適用後も、全8軸を含む正当なACCEPT Resultは引き続き構築できる)。
    result = FaithfulnessVerificationResult(
        status=FaithfulnessVerificationStatus.SUCCESS,
        overall_outcome=FaithfulnessOutcome.ACCEPT,
        dimension_results=_full_accept_dimension_results(),
        candidate_reference="CANDREF_x",
        verification_version=DETERMINISTIC_FAITHFULNESS_VERSION,
        verified_at=_VERIFIED_AT,
    )
    assert result.status == FaithfulnessVerificationStatus.SUCCESS


# ============================================================
# D0102.4.1.2 — Final Deterministic Faithfulness Closure(F02/F04/F05)
#
# D0102.4.1.1閉鎖後のNarrow Codex Adversarial Audit(D0102.4.1.1.1)で
# 再発見されたF02(Unsafe Partial Numeric Extraction)・F04(Mixed
# Direction Silent PASS)・F05(Temporal Borrowing)の3件を、Public
# Entrypoint経由でDimension単位でも直接Assertする。
# ============================================================


# ---- F02: Malformed Numeric Partial Extraction Guard ----


def test_d0102412_f02_1_ascii_minus_sign_mismatch_remains_rejected() -> None:
    doc, span = _doc_and_span("-3.7%の損失が生じる可能性がある。", taxonomy_name=_BUSINESS_RISK_TAXONOMY)
    candidate = _candidate(
        evidence_span=span, claim_type=SemanticClaimType.BUSINESS_RISK, text="3.7%の損失が生じる可能性がある。"
    )

    result = verify_candidate_deterministically(candidate=candidate, document=doc, verified_at=_VERIFIED_AT)

    quantity = _dim_result(result, FaithfulnessDimension.QUANTITY)
    assert quantity.outcome == FaithfulnessDimensionOutcome.FAIL
    assert quantity.reason_code == FaithfulnessReasonCode.QUANTITY_SIGN_MISMATCH
    assert result.overall_outcome == FaithfulnessOutcome.REJECT


def test_d0102412_f02_2_malformed_comma_numeral_cannot_partially_become_trusted() -> None:
    # 「1,23円」の先頭「1,」を黙って読み飛ばして「23円」だけを信頼できる
    # 数量として扱うことを禁止する(D0102.4.1.2 §3B)。Candidateが偶然その
    # Tailと一致していても、overallはACCEPTしてはならない。
    doc, span = _doc_and_span("損失は1,23円になる可能性がある。", taxonomy_name=_BUSINESS_RISK_TAXONOMY)
    candidate = _candidate(evidence_span=span, claim_type=SemanticClaimType.BUSINESS_RISK, text="23円になる可能性がある。")

    result = verify_candidate_deterministically(candidate=candidate, document=doc, verified_at=_VERIFIED_AT)

    quantity = _dim_result(result, FaithfulnessDimension.QUANTITY)
    assert quantity.outcome == FaithfulnessDimensionOutcome.AMBIGUOUS
    assert quantity.reason_code == FaithfulnessReasonCode.UNPARSED_NUMERIC_CONTENT
    assert result.overall_outcome != FaithfulnessOutcome.ACCEPT


def test_d0102412_f02_3_fullwidth_percent_unsupported_fails_closed() -> None:
    text = "４.０％の増加があった。"
    doc, span = _doc_and_span(text)
    candidate = _candidate(evidence_span=span, text=text)

    result = verify_candidate_deterministically(candidate=candidate, document=doc, verified_at=_VERIFIED_AT)

    quantity = _dim_result(result, FaithfulnessDimension.QUANTITY)
    assert quantity.outcome == FaithfulnessDimensionOutcome.AMBIGUOUS
    assert quantity.reason_code == FaithfulnessReasonCode.UNPARSED_NUMERIC_CONTENT
    assert result.overall_outcome != FaithfulnessOutcome.ACCEPT


def test_d0102412_f02_4_unsupported_scale_kanji_fails_closed() -> None:
    text = "3百万円の増加があった。"
    doc, span = _doc_and_span(text)
    candidate = _candidate(evidence_span=span, text=text)

    result = verify_candidate_deterministically(candidate=candidate, document=doc, verified_at=_VERIFIED_AT)

    quantity = _dim_result(result, FaithfulnessDimension.QUANTITY)
    assert quantity.outcome == FaithfulnessDimensionOutcome.AMBIGUOUS
    assert quantity.reason_code == FaithfulnessReasonCode.UNPARSED_NUMERIC_CONTENT
    assert result.overall_outcome != FaithfulnessOutcome.ACCEPT


# ---- F04: Mixed Direction Must Be an Explicit State ----


def test_d0102412_f04_5_mixed_direction_with_unspecified_reviews_not_accepts() -> None:
    text = "売上高は増加し、利益は減少する可能性がある。"
    doc, span = _doc_and_span(text, taxonomy_name=_BUSINESS_RISK_TAXONOMY)
    candidate = _candidate(
        evidence_span=span, claim_type=SemanticClaimType.BUSINESS_RISK, text=text, direction=ClaimDirection.UNSPECIFIED
    )

    result = verify_candidate_deterministically(candidate=candidate, document=doc, verified_at=_VERIFIED_AT)

    prop = _dim_result(result, FaithfulnessDimension.PROPOSITION_IDENTITY)
    assert prop.outcome == FaithfulnessDimensionOutcome.AMBIGUOUS
    assert prop.reason_code == FaithfulnessReasonCode.DIRECTION_REQUIRES_SEMANTIC_REVIEW
    assert result.overall_outcome == FaithfulnessOutcome.REVIEW_REQUIRED
    assert result.overall_outcome != FaithfulnessOutcome.ACCEPT


def test_d0102412_f04_6_mixed_direction_with_increase_reviews_not_passes() -> None:
    text = "売上高は増加し、利益は減少した。"
    doc, span = _doc_and_span(text, taxonomy_name=_BUSINESS_RISK_TAXONOMY)
    candidate = _candidate(
        evidence_span=span, claim_type=SemanticClaimType.BUSINESS_RISK, text=text, direction=ClaimDirection.INCREASE
    )

    result = verify_candidate_deterministically(candidate=candidate, document=doc, verified_at=_VERIFIED_AT)

    prop = _dim_result(result, FaithfulnessDimension.PROPOSITION_IDENTITY)
    assert prop.outcome == FaithfulnessDimensionOutcome.AMBIGUOUS
    assert prop.reason_code == FaithfulnessReasonCode.DIRECTION_REQUIRES_SEMANTIC_REVIEW


def test_d0102412_f04_7_negated_increase_with_increase_direction_remains_review() -> None:
    text = "リスクは増加しない。対策を実施している。"
    doc, span = _doc_and_span(text, taxonomy_name=_BUSINESS_RISK_TAXONOMY)
    candidate = _candidate(
        evidence_span=span, claim_type=SemanticClaimType.BUSINESS_RISK, text=text, direction=ClaimDirection.INCREASE
    )

    result = verify_candidate_deterministically(candidate=candidate, document=doc, verified_at=_VERIFIED_AT)

    prop = _dim_result(result, FaithfulnessDimension.PROPOSITION_IDENTITY)
    assert prop.outcome != FaithfulnessDimensionOutcome.PASS
    assert prop.reason_code == FaithfulnessReasonCode.DIRECTION_REQUIRES_SEMANTIC_REVIEW
    assert result.overall_outcome != FaithfulnessOutcome.ACCEPT


def test_d0102412_f04_8_single_clean_increase_still_passes() -> None:
    text = "売上高は増加した。"
    doc, span = _doc_and_span(text, taxonomy_name=_BUSINESS_RISK_TAXONOMY)
    candidate = _candidate(
        evidence_span=span, claim_type=SemanticClaimType.BUSINESS_RISK, text=text, direction=ClaimDirection.INCREASE
    )

    result = verify_candidate_deterministically(candidate=candidate, document=doc, verified_at=_VERIFIED_AT)

    prop = _dim_result(result, FaithfulnessDimension.PROPOSITION_IDENTITY)
    assert prop.outcome == FaithfulnessDimensionOutcome.PASS


def test_d0102412_f04_9_clean_direction_contradiction_still_rejects() -> None:
    text = "利益は減少した。"
    doc, span = _doc_and_span(text, taxonomy_name=_BUSINESS_RISK_TAXONOMY)
    candidate = _candidate(
        evidence_span=span, claim_type=SemanticClaimType.BUSINESS_RISK, text=text, direction=ClaimDirection.INCREASE
    )

    result = verify_candidate_deterministically(candidate=candidate, document=doc, verified_at=_VERIFIED_AT)

    prop = _dim_result(result, FaithfulnessDimension.PROPOSITION_IDENTITY)
    assert prop.outcome == FaithfulnessDimensionOutcome.FAIL
    assert prop.reason_code == FaithfulnessReasonCode.DIRECTION_MISMATCH_DETECTED
    assert result.overall_outcome == FaithfulnessOutcome.REJECT


# ---- F05: Temporal Local Binding ----


def test_d0102412_f05_10_original_multi_temporal_false_reject_stays_closed() -> None:
    doc, span = _doc_and_span("現在のリスクを分析した。今後損失が生じる可能性がある。", taxonomy_name=_BUSINESS_RISK_TAXONOMY)
    candidate = _candidate(evidence_span=span, claim_type=SemanticClaimType.BUSINESS_RISK, text="今後損失が生じる可能性がある。")

    result = verify_candidate_deterministically(candidate=candidate, document=doc, verified_at=_VERIFIED_AT)

    temporal = _dim_result(result, FaithfulnessDimension.TEMPORAL_SCOPE)
    assert temporal.outcome != FaithfulnessDimensionOutcome.FAIL
    assert result.overall_outcome != FaithfulnessOutcome.REJECT


def test_d0102412_f05_11_unrelated_future_marker_cannot_certify_sales_proposition() -> None:
    # F05 Temporal Borrowing Repro: 「今後」は別事業のRiskにのみ係っており、
    # 販売のFUTURE Scopeを証明しない(D0102.4.1.2 §5D)。
    doc, span = _doc_and_span(
        "現在の販売は堅調である。今後、別事業では損失が生じる可能性がある。", taxonomy_name=_BUSINESS_RISK_TAXONOMY
    )
    candidate = _candidate(evidence_span=span, claim_type=SemanticClaimType.OUTLOOK, text="今後、販売は堅調である。")

    result = verify_candidate_deterministically(candidate=candidate, document=doc, verified_at=_VERIFIED_AT)

    temporal = _dim_result(result, FaithfulnessDimension.TEMPORAL_SCOPE)
    assert temporal.outcome == FaithfulnessDimensionOutcome.AMBIGUOUS
    assert temporal.reason_code == FaithfulnessReasonCode.TEMPORAL_REQUIRES_SEMANTIC_REVIEW
    assert result.overall_outcome != FaithfulnessOutcome.ACCEPT


def test_d0102412_f05_12_pure_historical_future_claim_still_fails() -> None:
    doc, span = _doc_and_span("当中間連結会計期間の業績は堅調であった。", taxonomy_name=_BUSINESS_RISK_TAXONOMY)
    candidate = _candidate(evidence_span=span, claim_type=SemanticClaimType.OUTLOOK, text="今後も継続的に堅調である。")

    result = verify_candidate_deterministically(candidate=candidate, document=doc, verified_at=_VERIFIED_AT)

    temporal = _dim_result(result, FaithfulnessDimension.TEMPORAL_SCOPE)
    assert temporal.outcome == FaithfulnessDimensionOutcome.FAIL
    assert temporal.reason_code == FaithfulnessReasonCode.TEMPORAL_CATEGORY_MISMATCH


def test_d0102412_f05_13_multiple_categories_without_local_binding_is_ambiguous() -> None:
    # 「販売」節にはHISTORICALしか係っておらず、別節の「今後」をBorrowして
    # FUTUREのSubject Attribution Claimを証明することはできない。
    doc, span = _doc_and_span("現在の販売は堅調である。今後、他事業の縮小を検討している。", taxonomy_name=_BUSINESS_RISK_TAXONOMY)
    candidate = _candidate(
        evidence_span=span, claim_type=SemanticClaimType.MANAGEMENT_EXPLANATION, text="今後、販売の縮小を検討している。"
    )

    result = verify_candidate_deterministically(candidate=candidate, document=doc, verified_at=_VERIFIED_AT)

    temporal = _dim_result(result, FaithfulnessDimension.TEMPORAL_SCOPE)
    assert temporal.outcome == FaithfulnessDimensionOutcome.AMBIGUOUS
    assert temporal.reason_code == FaithfulnessReasonCode.TEMPORAL_REQUIRES_SEMANTIC_REVIEW
    assert result.overall_outcome != FaithfulnessOutcome.ACCEPT


# ============================================================
# D0102.4.2 — Model-Assisted Verification + ACCEPT-only Promotion
#
# `FakeVerifier`はDeterministicなTest Double(実LLM/Vendor SDK不使用、
# `MODEL_CALL_SITES = 0`)。各TestはPublic Entrypoint
# (`verify_candidate_faithfulness()`/`promote_verified_candidate()`)を
# 通じてのみ検証する。
# ============================================================


class FakeVerifier:
    """`FaithfulnessVerifier` Protocolを満たすDeterministic Test
    Double。`response`は固定Dict、または`verifier_input`を受け取り
    Dictを返すCallable。呼び出し回数・最後の入力を記録する(Source
    Revalidation Timing/Narrow Input Allowlistの検証用)。"""

    def __init__(self, response=None, *, raise_exc: Exception | None = None) -> None:
        self.response = response
        self.raise_exc = raise_exc
        self.call_count = 0
        self.last_input: FaithfulnessVerifierInput | None = None

    def verify(self, *, verifier_input: FaithfulnessVerifierInput) -> object:
        self.call_count += 1
        self.last_input = verifier_input
        if self.raise_exc is not None:
            raise self.raise_exc
        if callable(self.response):
            return self.response(verifier_input)
        return self.response


def _verify_model_assisted(
    *,
    candidate: SemanticClaimCandidate,
    document: NormalizedDisclosureDocument,
    verifier: FakeVerifier,
) -> FaithfulnessVerificationResult:
    return verify_candidate_faithfulness(
        candidate=candidate,
        document=document,
        verifier=verifier,
        model_provider="test-provider",
        model_name="test-model",
        prompt_hash="test-prompt-hash",
        verified_at=_VERIFIED_AT,
    )


def _dims(*entries: tuple[str, str, str]) -> dict:
    return {"dimensions": [{"dimension": d, "outcome": o, "reason_code": r} for d, o, r in entries]}


# ---- Toyota Acceptance Fixtures(D0102.4 §34、Case A-O + P/Q/R/S/T) ----


def test_case_a_exact_supported_quote_accepts_without_model_call() -> None:
    text = "為替の影響により、利益が減少する可能性がある。"
    doc, span = _doc_and_span(text, taxonomy_name=_BUSINESS_RISK_TAXONOMY)
    candidate = _candidate(
        evidence_span=span, claim_type=SemanticClaimType.BUSINESS_RISK, text=text, direction=ClaimDirection.DECREASE
    )
    verifier = FakeVerifier(response=_dims())

    result = _verify_model_assisted(candidate=candidate, document=doc, verifier=verifier)

    assert verifier.call_count == 0
    assert result.status == FaithfulnessVerificationStatus.SUCCESS
    assert result.overall_outcome == FaithfulnessOutcome.ACCEPT
    assert result.verification_provenance is None


def test_case_b_faithful_paraphrase_ratified_by_approved_table_accepts() -> None:
    evidence_text = "海外事業の販売が拡大した可能性がある。"
    candidate_text = "海外事業の販売が伸びた可能性がある。"
    doc, span = _doc_and_span(evidence_text, taxonomy_name=_BUSINESS_RISK_TAXONOMY)
    candidate = _candidate(evidence_span=span, claim_type=SemanticClaimType.BUSINESS_RISK, text=candidate_text)
    verifier = FakeVerifier(
        response=_dims(
            ("PROPOSITION_IDENTITY", "PASS", "NO_ISSUE_DETECTED"),
            ("SUBJECT_ATTRIBUTION", "PASS", "NO_ISSUE_DETECTED"),
            ("SCOPE", "PASS", "NO_ISSUE_DETECTED"),
        )
    )

    result = _verify_model_assisted(candidate=candidate, document=doc, verifier=verifier)

    assert verifier.call_count == 1
    assert result.overall_outcome == FaithfulnessOutcome.ACCEPT
    prop = _dim_result(result, FaithfulnessDimension.PROPOSITION_IDENTITY)
    assert prop.outcome == FaithfulnessDimensionOutcome.PASS
    assert prop.reason_code == FaithfulnessReasonCode.PARAPHRASE_EQUIVALENT_CONFIRMED
    assert prop.checked_by == FaithfulnessCheckMethod.MODEL
    assert result.verification_provenance is not None
    assert result.verification_provenance.model_provider == "test-provider"


def test_unratified_paraphrase_pass_downgrades_to_ambiguous_not_accept() -> None:
    # Bの回帰Test: 事前承認済みTableに無いPairについては、ModelがPASSを
    # 提案してもDeterministicにRatifyできず、overallはACCEPTしない。
    evidence_text = "海外事業の販売が拡大した可能性がある。"
    candidate_text = "海外事業の商品需要が高まった可能性がある。"
    doc, span = _doc_and_span(evidence_text, taxonomy_name=_BUSINESS_RISK_TAXONOMY)
    candidate = _candidate(evidence_span=span, claim_type=SemanticClaimType.BUSINESS_RISK, text=candidate_text)
    verifier = FakeVerifier(
        response=_dims(
            ("PROPOSITION_IDENTITY", "PASS", "NO_ISSUE_DETECTED"),
            ("SUBJECT_ATTRIBUTION", "PASS", "NO_ISSUE_DETECTED"),
            ("SCOPE", "PASS", "NO_ISSUE_DETECTED"),
        )
    )

    result = _verify_model_assisted(candidate=candidate, document=doc, verifier=verifier)

    prop = _dim_result(result, FaithfulnessDimension.PROPOSITION_IDENTITY)
    assert prop.outcome == FaithfulnessDimensionOutcome.AMBIGUOUS
    assert prop.reason_code == FaithfulnessReasonCode.SEMANTIC_VERIFICATION_REQUIRED
    assert result.overall_outcome != FaithfulnessOutcome.ACCEPT


def test_case_c_wrong_subject_rejects() -> None:
    evidence_text = "金融事業の利益は増加した可能性がある。"
    candidate_text = "製造事業の利益は増加した可能性がある。"
    doc, span = _doc_and_span(evidence_text, taxonomy_name=_BUSINESS_RISK_TAXONOMY)
    candidate = _candidate(
        evidence_span=span, claim_type=SemanticClaimType.BUSINESS_RISK, text=candidate_text, direction=ClaimDirection.INCREASE
    )
    verifier = FakeVerifier(
        response=_dims(
            ("PROPOSITION_IDENTITY", "AMBIGUOUS", "SEMANTIC_VERIFICATION_REQUIRED"),
            ("SUBJECT_ATTRIBUTION", "FAIL", "SUBJECT_MISMATCH_DETECTED"),
            ("SCOPE", "PASS", "NO_ISSUE_DETECTED"),
        )
    )

    result = _verify_model_assisted(candidate=candidate, document=doc, verifier=verifier)

    subject = _dim_result(result, FaithfulnessDimension.SUBJECT_ATTRIBUTION)
    assert subject.outcome == FaithfulnessDimensionOutcome.FAIL
    assert result.overall_outcome == FaithfulnessOutcome.REJECT


def test_case_d_opposite_direction_rejects_without_model_call() -> None:
    text = "リスクは増加した。"
    doc, span = _doc_and_span(text, taxonomy_name=_BUSINESS_RISK_TAXONOMY)
    candidate = _candidate(
        evidence_span=span, claim_type=SemanticClaimType.BUSINESS_RISK, text=text, direction=ClaimDirection.DECREASE
    )
    verifier = FakeVerifier(response=_dims())

    result = _verify_model_assisted(candidate=candidate, document=doc, verifier=verifier)

    assert verifier.call_count == 0
    assert result.overall_outcome == FaithfulnessOutcome.REJECT


def test_case_e_negation_inversion_rejects_without_model_call() -> None:
    doc, span = _doc_and_span("重要な変更はありません。", taxonomy_name=_BUSINESS_RISK_TAXONOMY)
    candidate = _candidate(evidence_span=span, claim_type=SemanticClaimType.BUSINESS_RISK, text="重要な変更があった。")
    verifier = FakeVerifier(response=_dims())

    result = _verify_model_assisted(candidate=candidate, document=doc, verifier=verifier)

    assert verifier.call_count == 0
    assert result.overall_outcome == FaithfulnessOutcome.REJECT


def test_case_f_wrong_temporal_period_rejects_even_if_model_passes_other_dims() -> None:
    doc, span = _doc_and_span("当中間連結会計期間の業績は堅調であった。")
    candidate = _candidate(evidence_span=span, claim_type=SemanticClaimType.OUTLOOK, text="今後も継続的に堅調である。")
    verifier = FakeVerifier(
        response=_dims(
            ("PROPOSITION_IDENTITY", "PASS", "NO_ISSUE_DETECTED"),
            ("SUBJECT_ATTRIBUTION", "PASS", "NO_ISSUE_DETECTED"),
            ("SCOPE", "PASS", "NO_ISSUE_DETECTED"),
            ("CERTAINTY_AND_COMMITMENT", "PASS", "NO_ISSUE_DETECTED"),
        )
    )

    result = _verify_model_assisted(candidate=candidate, document=doc, verifier=verifier)

    temporal = _dim_result(result, FaithfulnessDimension.TEMPORAL_SCOPE)
    assert temporal.outcome == FaithfulnessDimensionOutcome.FAIL
    assert temporal.checked_by == FaithfulnessCheckMethod.DETERMINISTIC
    assert result.overall_outcome == FaithfulnessOutcome.REJECT


def test_case_g_causal_tier_upgrade_rejects_even_if_model_passes_other_dims() -> None:
    doc, span = _doc_and_span("為替影響は一因である。")
    candidate = _candidate(
        evidence_span=span, claim_type=SemanticClaimType.PERFORMANCE_DRIVER, text="為替影響は唯一の原因である。"
    )
    verifier = FakeVerifier(
        response=_dims(
            ("PROPOSITION_IDENTITY", "PASS", "NO_ISSUE_DETECTED"),
            ("SUBJECT_ATTRIBUTION", "PASS", "NO_ISSUE_DETECTED"),
            ("SCOPE", "PASS", "NO_ISSUE_DETECTED"),
        )
    )

    result = _verify_model_assisted(candidate=candidate, document=doc, verifier=verifier)

    causal = _dim_result(result, FaithfulnessDimension.CAUSAL_STRENGTH)
    assert causal.outcome == FaithfulnessDimensionOutcome.FAIL
    assert causal.checked_by == FaithfulnessCheckMethod.DETERMINISTIC
    assert result.overall_outcome == FaithfulnessOutcome.REJECT


def test_case_h_certainty_tier_upgrade_rejects_even_if_model_passes_other_dims() -> None:
    doc, span = _doc_and_span("損失が発生する可能性がある。", taxonomy_name=_BUSINESS_RISK_TAXONOMY)
    candidate = _candidate(evidence_span=span, claim_type=SemanticClaimType.BUSINESS_RISK, text="損失が発生する。")
    verifier = FakeVerifier(
        response=_dims(
            ("PROPOSITION_IDENTITY", "PASS", "NO_ISSUE_DETECTED"),
            ("SUBJECT_ATTRIBUTION", "PASS", "NO_ISSUE_DETECTED"),
            ("SCOPE", "PASS", "NO_ISSUE_DETECTED"),
        )
    )

    result = _verify_model_assisted(candidate=candidate, document=doc, verifier=verifier)

    certainty = _dim_result(result, FaithfulnessDimension.CERTAINTY_AND_COMMITMENT)
    assert certainty.outcome == FaithfulnessDimensionOutcome.FAIL
    assert certainty.checked_by == FaithfulnessCheckMethod.DETERMINISTIC
    assert result.overall_outcome == FaithfulnessOutcome.REJECT


def test_case_i_invented_number_rejects_without_model_call() -> None:
    doc, span = _doc_and_span("業績は堅調に推移した。")
    candidate = _candidate(evidence_span=span, claim_type=SemanticClaimType.PERFORMANCE_CHANGE, text="業績は4.0%増加した。")
    verifier = FakeVerifier(response=_dims())

    result = _verify_model_assisted(candidate=candidate, document=doc, verifier=verifier)

    assert verifier.call_count == 0
    assert result.overall_outcome == FaithfulnessOutcome.REJECT


def test_case_j_genuine_ambiguity_reviews() -> None:
    doc, span = _doc_and_span("業績は堅調に推移した可能性がある。", taxonomy_name=_BUSINESS_RISK_TAXONOMY)
    candidate = _candidate(
        evidence_span=span, claim_type=SemanticClaimType.BUSINESS_RISK, text="業績はやや上向いた可能性がある。"
    )
    verifier = FakeVerifier(
        response=_dims(
            ("PROPOSITION_IDENTITY", "AMBIGUOUS", "SEMANTIC_VERIFICATION_REQUIRED"),
            ("SUBJECT_ATTRIBUTION", "AMBIGUOUS", "SEMANTIC_VERIFICATION_REQUIRED"),
            ("SCOPE", "PASS", "NO_ISSUE_DETECTED"),
        )
    )

    result = _verify_model_assisted(candidate=candidate, document=doc, verifier=verifier)

    assert result.overall_outcome == FaithfulnessOutcome.REVIEW_REQUIRED


def test_case_n_correct_text_wrong_claim_type_rejects() -> None:
    text = "業績は堅調に推移した。"
    doc, span = _doc_and_span(text)
    candidate = _candidate(evidence_span=span, claim_type=SemanticClaimType.CAPITAL_ALLOCATION, text=text)
    verifier = FakeVerifier(
        response=_dims(
            ("PROPOSITION_IDENTITY", "FAIL", "PROPOSITION_SEMANTIC_MISMATCH_DETECTED"),
            ("CERTAINTY_AND_COMMITMENT", "PASS", "NO_ISSUE_DETECTED"),
        )
    )

    result = _verify_model_assisted(candidate=candidate, document=doc, verifier=verifier)

    prop = _dim_result(result, FaithfulnessDimension.PROPOSITION_IDENTITY)
    assert prop.outcome == FaithfulnessDimensionOutcome.FAIL
    assert result.overall_outcome == FaithfulnessOutcome.REJECT


def test_case_o_materially_broadened_scope_is_caught_despite_substring_trivial_pass() -> None:
    # Candidateは Evidence の厳密な部分文字列(「北米事業」限定を落として
    # いる)——`_check_scope()`自体はTrivial PASSするが、完全一致では
    # ないためScopeはModelへ回され、Qualifier脱落をFAILとして検出する。
    evidence_text = "北米事業の販売は拡大した可能性がある。"
    candidate_text = "販売は拡大した可能性がある。"
    doc, span = _doc_and_span(evidence_text, taxonomy_name=_BUSINESS_RISK_TAXONOMY)
    candidate = _candidate(evidence_span=span, claim_type=SemanticClaimType.BUSINESS_RISK, text=candidate_text)
    verifier = FakeVerifier(response=_dims(("SCOPE", "FAIL", "SCOPE_QUALIFIER_DROPPED")))

    result = _verify_model_assisted(candidate=candidate, document=doc, verifier=verifier)

    assert verifier.call_count == 1
    scope = _dim_result(result, FaithfulnessDimension.SCOPE)
    assert scope.outcome == FaithfulnessDimensionOutcome.FAIL
    assert scope.checked_by == FaithfulnessCheckMethod.MODEL
    assert result.overall_outcome == FaithfulnessOutcome.REVIEW_REQUIRED


def test_case_p_deterministic_fail_wins_over_hypothetical_model_pass() -> None:
    # ModelがPASSしか返さないVerifierでも、Hard-Fail軸が既に
    # Deterministic FAIL確定していればModelは一切呼び出されない。
    doc, span = _doc_and_span("重要な変更はありません。", taxonomy_name=_BUSINESS_RISK_TAXONOMY)
    candidate = _candidate(evidence_span=span, claim_type=SemanticClaimType.BUSINESS_RISK, text="重要な変更があった。")
    verifier = FakeVerifier(response=_dims())

    result = _verify_model_assisted(candidate=candidate, document=doc, verifier=verifier)

    assert verifier.call_count == 0
    assert result.overall_outcome == FaithfulnessOutcome.REJECT


def test_case_q_review_required_never_promotes() -> None:
    doc, span = _doc_and_span("業績は堅調に推移した可能性がある。", taxonomy_name=_BUSINESS_RISK_TAXONOMY)
    candidate = _candidate(
        evidence_span=span, claim_type=SemanticClaimType.BUSINESS_RISK, text="業績はやや上向いた可能性がある。"
    )
    verifier = FakeVerifier(
        response=_dims(
            ("PROPOSITION_IDENTITY", "AMBIGUOUS", "SEMANTIC_VERIFICATION_REQUIRED"),
            ("SUBJECT_ATTRIBUTION", "PASS", "NO_ISSUE_DETECTED"),
            ("SCOPE", "PASS", "NO_ISSUE_DETECTED"),
        )
    )

    result = _verify_model_assisted(candidate=candidate, document=doc, verifier=verifier)
    assert result.overall_outcome == FaithfulnessOutcome.REVIEW_REQUIRED

    claim = promote_verified_candidate(candidate=candidate, verification_result=result)

    assert claim is None


def test_case_r_reject_never_promotes() -> None:
    doc, span = _doc_and_span("重要な変更はありません。", taxonomy_name=_BUSINESS_RISK_TAXONOMY)
    candidate = _candidate(evidence_span=span, claim_type=SemanticClaimType.BUSINESS_RISK, text="重要な変更があった。")
    verifier = FakeVerifier(response=_dims())

    result = _verify_model_assisted(candidate=candidate, document=doc, verifier=verifier)
    assert result.overall_outcome == FaithfulnessOutcome.REJECT

    claim = promote_verified_candidate(candidate=candidate, verification_result=result)

    assert claim is None


def test_case_s_accept_promotes_preserving_exact_candidate_fields() -> None:
    text = "為替の影響により、利益が減少する可能性がある。"
    doc, span = _doc_and_span(text, taxonomy_name=_BUSINESS_RISK_TAXONOMY)
    candidate = _candidate(
        evidence_span=span, claim_type=SemanticClaimType.BUSINESS_RISK, text=text, direction=ClaimDirection.DECREASE
    )
    verifier = FakeVerifier(response=_dims())

    result = _verify_model_assisted(candidate=candidate, document=doc, verifier=verifier)
    assert result.overall_outcome == FaithfulnessOutcome.ACCEPT

    claim = promote_verified_candidate(candidate=candidate, verification_result=result)

    assert claim is not None
    assert claim.claim_type == candidate.claim_type
    assert claim.normalized_claim_text == candidate.normalized_claim_text
    assert claim.direction == candidate.direction
    assert claim.evidence_span == candidate.evidence_span
    assert claim.extraction_version == candidate.extraction_version
    assert claim.schema_version == candidate.schema_version
    assert claim.extraction_provenance == candidate.extraction_provenance
    assert claim.faithfulness_outcome == FaithfulnessOutcome.ACCEPT
    assert claim.faithfulness_review_required is False


def test_case_t_verifier_rewrite_field_is_contract_violation() -> None:
    doc, span = _doc_and_span("業績は堅調に推移した可能性がある。", taxonomy_name=_BUSINESS_RISK_TAXONOMY)
    candidate = _candidate(
        evidence_span=span, claim_type=SemanticClaimType.BUSINESS_RISK, text="業績はやや上向いた可能性がある。"
    )
    verifier = FakeVerifier(
        response={
            "dimensions": [
                {
                    "dimension": "PROPOSITION_IDENTITY",
                    "outcome": "PASS",
                    "reason_code": "NO_ISSUE_DETECTED",
                    "corrected_claim_text": "hacked",
                }
            ]
        }
    )

    result = _verify_model_assisted(candidate=candidate, document=doc, verifier=verifier)

    assert result.status == FaithfulnessVerificationStatus.VERIFIER_CONTRACT_VIOLATION
    assert result.overall_outcome is None


def test_case_l_verifier_exception_is_verifier_error() -> None:
    doc, span = _doc_and_span("業績は堅調に推移した可能性がある。", taxonomy_name=_BUSINESS_RISK_TAXONOMY)
    candidate = _candidate(
        evidence_span=span, claim_type=SemanticClaimType.BUSINESS_RISK, text="業績はやや上向いた可能性がある。"
    )
    verifier = FakeVerifier(raise_exc=RuntimeError("boom"))

    result = _verify_model_assisted(candidate=candidate, document=doc, verifier=verifier)

    assert result.status == FaithfulnessVerificationStatus.VERIFIER_ERROR
    assert result.overall_outcome is None
    assert result.dimension_results == ()


def test_case_m_stale_evidence_span_blocks_model_call() -> None:
    doc, span = _doc_and_span("本文です。", taxonomy_name=_BUSINESS_RISK_TAXONOMY)
    stale_span = replace(span, source_normalizer_version="STALE_VERSION_DOES_NOT_MATCH")
    candidate = _candidate(evidence_span=stale_span, claim_type=SemanticClaimType.BUSINESS_RISK, text="本文です。")
    verifier = FakeVerifier(response=_dims())

    result = _verify_model_assisted(candidate=candidate, document=doc, verifier=verifier)

    assert result.status == FaithfulnessVerificationStatus.SOURCE_REVALIDATION_FAILED
    assert result.overall_outcome is None
    assert verifier.call_count == 0


def test_candidate_integrity_gate_rejects_non_candidate_object_model_assisted() -> None:
    doc, _span = _doc_and_span("本文です。")
    verifier = FakeVerifier(response=_dims())

    result = verify_candidate_faithfulness(
        candidate={"not": "a candidate"},
        document=doc,
        verifier=verifier,
        model_provider="p",
        model_name="m",
        prompt_hash="h",
        verified_at=_VERIFIED_AT,
    )

    assert result.status == FaithfulnessVerificationStatus.CANDIDATE_INTEGRITY_FAILED
    assert result.overall_outcome is None
    assert verifier.call_count == 0


def test_prompt_hash_required_raises_schema_error() -> None:
    doc, span = _doc_and_span("本文です。", taxonomy_name=_BUSINESS_RISK_TAXONOMY)
    candidate = _candidate(evidence_span=span, claim_type=SemanticClaimType.BUSINESS_RISK, text="本文です。")
    verifier = FakeVerifier(response=_dims())

    with pytest.raises(FaithfulnessSchemaError):
        verify_candidate_faithfulness(
            candidate=candidate,
            document=doc,
            verifier=verifier,
            model_provider="p",
            model_name="m",
            prompt_hash="",
            verified_at=_VERIFIED_AT,
        )


# ---- Model Contract Tests(D0102.4 §14) ----


def _run_with_raw_response(raw_response: object) -> FaithfulnessVerificationResult:
    doc, span = _doc_and_span("業績は堅調に推移した可能性がある。", taxonomy_name=_BUSINESS_RISK_TAXONOMY)
    candidate = _candidate(
        evidence_span=span, claim_type=SemanticClaimType.BUSINESS_RISK, text="業績はやや上向いた可能性がある。"
    )
    verifier = FakeVerifier(response=raw_response)
    return _verify_model_assisted(candidate=candidate, document=doc, verifier=verifier)


def test_contract_unknown_top_level_key_is_violation() -> None:
    result = _run_with_raw_response({"dimensions": [], "confidence": 0.9})
    assert result.status == FaithfulnessVerificationStatus.VERIFIER_CONTRACT_VIOLATION
    assert result.overall_outcome is None


def test_contract_unknown_item_field_is_violation() -> None:
    result = _run_with_raw_response(
        {
            "dimensions": [
                {"dimension": "PROPOSITION_IDENTITY", "outcome": "PASS", "reason_code": "NO_ISSUE_DETECTED", "summary": "x"}
            ]
        }
    )
    assert result.status == FaithfulnessVerificationStatus.VERIFIER_CONTRACT_VIOLATION


def test_contract_missing_requested_dimension_is_violation() -> None:
    # 必要な3軸(PROPOSITION_IDENTITY/SUBJECT_ATTRIBUTION/SCOPE)のうち
    # 1件のみ返す——欠落。
    result = _run_with_raw_response(
        {"dimensions": [{"dimension": "PROPOSITION_IDENTITY", "outcome": "PASS", "reason_code": "NO_ISSUE_DETECTED"}]}
    )
    assert result.status == FaithfulnessVerificationStatus.VERIFIER_CONTRACT_VIOLATION


def test_contract_duplicate_dimension_is_violation() -> None:
    result = _run_with_raw_response(
        _dims(
            ("PROPOSITION_IDENTITY", "PASS", "NO_ISSUE_DETECTED"),
            ("PROPOSITION_IDENTITY", "PASS", "NO_ISSUE_DETECTED"),
            ("SUBJECT_ATTRIBUTION", "PASS", "NO_ISSUE_DETECTED"),
            ("SCOPE", "PASS", "NO_ISSUE_DETECTED"),
        )
    )
    assert result.status == FaithfulnessVerificationStatus.VERIFIER_CONTRACT_VIOLATION


def test_contract_extra_unrequested_dimension_is_violation() -> None:
    result = _run_with_raw_response(
        _dims(
            ("PROPOSITION_IDENTITY", "PASS", "NO_ISSUE_DETECTED"),
            ("SUBJECT_ATTRIBUTION", "PASS", "NO_ISSUE_DETECTED"),
            ("SCOPE", "PASS", "NO_ISSUE_DETECTED"),
            ("QUANTITY", "PASS", "NO_ISSUE_DETECTED"),
        )
    )
    assert result.status == FaithfulnessVerificationStatus.VERIFIER_CONTRACT_VIOLATION


def test_contract_unknown_dimension_enum_is_violation() -> None:
    result = _run_with_raw_response(
        {"dimensions": [{"dimension": "NOT_A_REAL_DIMENSION", "outcome": "PASS", "reason_code": "NO_ISSUE_DETECTED"}]}
    )
    assert result.status == FaithfulnessVerificationStatus.VERIFIER_CONTRACT_VIOLATION


def test_contract_unknown_outcome_enum_is_violation() -> None:
    result = _run_with_raw_response(
        {"dimensions": [{"dimension": "PROPOSITION_IDENTITY", "outcome": "MAYBE", "reason_code": "NO_ISSUE_DETECTED"}]}
    )
    assert result.status == FaithfulnessVerificationStatus.VERIFIER_CONTRACT_VIOLATION


def test_contract_unknown_reason_code_is_violation() -> None:
    result = _run_with_raw_response(
        {"dimensions": [{"dimension": "PROPOSITION_IDENTITY", "outcome": "PASS", "reason_code": "TOTALLY_MADE_UP"}]}
    )
    assert result.status == FaithfulnessVerificationStatus.VERIFIER_CONTRACT_VIOLATION


def test_contract_confidence_field_is_violation() -> None:
    result = _run_with_raw_response(
        {
            "dimensions": [
                {"dimension": "PROPOSITION_IDENTITY", "outcome": "PASS", "reason_code": "NO_ISSUE_DETECTED", "confidence": 0.95}
            ]
        }
    )
    assert result.status == FaithfulnessVerificationStatus.VERIFIER_CONTRACT_VIOLATION


def test_contract_rewrite_field_is_violation() -> None:
    result = _run_with_raw_response(
        {
            "dimensions": [
                {"dimension": "PROPOSITION_IDENTITY", "outcome": "PASS", "reason_code": "NO_ISSUE_DETECTED", "better_claim": "x"}
            ]
        }
    )
    assert result.status == FaithfulnessVerificationStatus.VERIFIER_CONTRACT_VIOLATION


def test_contract_top_level_not_dict_is_violation() -> None:
    result = _run_with_raw_response(["not", "a", "dict"])
    assert result.status == FaithfulnessVerificationStatus.VERIFIER_CONTRACT_VIOLATION


def test_contract_dimensions_not_list_is_violation() -> None:
    result = _run_with_raw_response({"dimensions": "PROPOSITION_IDENTITY"})
    assert result.status == FaithfulnessVerificationStatus.VERIFIER_CONTRACT_VIOLATION


def test_contract_not_applicable_on_never_not_applicable_dimension_is_violation() -> None:
    result = _run_with_raw_response(
        _dims(
            ("PROPOSITION_IDENTITY", "NOT_APPLICABLE", "NOT_APPLICABLE_NO_RELEVANT_CONTENT"),
            ("SUBJECT_ATTRIBUTION", "PASS", "NO_ISSUE_DETECTED"),
            ("SCOPE", "PASS", "NO_ISSUE_DETECTED"),
        )
    )
    assert result.status == FaithfulnessVerificationStatus.VERIFIER_CONTRACT_VIOLATION


# ---- Source Revalidation Timing(D0102.4 §9、Model呼び出し直前の再確認) ----


def test_source_revalidation_occurs_before_model_call_stale_span_blocks_call() -> None:
    doc, span = _doc_and_span("業績は堅調に推移した可能性がある。", taxonomy_name=_BUSINESS_RISK_TAXONOMY)
    stale_span = replace(span, source_normalizer_version="STALE_VERSION_DOES_NOT_MATCH")
    candidate = _candidate(
        evidence_span=stale_span, claim_type=SemanticClaimType.BUSINESS_RISK, text="業績はやや上向いた可能性がある。"
    )
    verifier = FakeVerifier(response=_dims())

    result = _verify_model_assisted(candidate=candidate, document=doc, verifier=verifier)

    assert result.status == FaithfulnessVerificationStatus.SOURCE_REVALIDATION_FAILED
    assert verifier.call_count == 0


def test_verifier_input_is_narrow_allowlist_only() -> None:
    evidence_text = "海外事業の販売が拡大した可能性がある。"
    doc, span = _doc_and_span(evidence_text, taxonomy_name=_BUSINESS_RISK_TAXONOMY)
    candidate = _candidate(
        evidence_span=span, claim_type=SemanticClaimType.BUSINESS_RISK, text="海外事業の販売が伸びた可能性がある。"
    )
    verifier = FakeVerifier(
        response=_dims(
            ("PROPOSITION_IDENTITY", "PASS", "NO_ISSUE_DETECTED"),
            ("SUBJECT_ATTRIBUTION", "PASS", "NO_ISSUE_DETECTED"),
            ("SCOPE", "PASS", "NO_ISSUE_DETECTED"),
        )
    )

    _verify_model_assisted(candidate=candidate, document=doc, verifier=verifier)

    assert verifier.last_input is not None
    field_names = set(FaithfulnessVerifierInput.__dataclass_fields__.keys())
    assert field_names == {"claim_type", "normalized_claim_text", "direction", "supporting_quote", "taxonomy_element_name"}
    assert verifier.last_input.claim_type == candidate.claim_type
    assert verifier.last_input.normalized_claim_text == candidate.normalized_claim_text
    assert verifier.last_input.direction == candidate.direction
    assert verifier.last_input.supporting_quote == evidence_text
    assert verifier.last_input.taxonomy_element_name == _BUSINESS_RISK_TAXONOMY


def test_verifier_input_rejects_wrong_types() -> None:
    with pytest.raises(FaithfulnessSchemaError):
        FaithfulnessVerifierInput(
            claim_type="BUSINESS_RISK",  # type: ignore[arg-type]
            normalized_claim_text="x",
            direction=ClaimDirection.UNSPECIFIED,
            supporting_quote="y",
            taxonomy_element_name="z",
        )


# ---- Provenance Tests(D0102.4 §27) ----


def test_deterministic_only_model_assisted_call_has_no_provenance() -> None:
    text = "為替の影響により、利益が減少する可能性がある。"
    doc, span = _doc_and_span(text, taxonomy_name=_BUSINESS_RISK_TAXONOMY)
    candidate = _candidate(
        evidence_span=span, claim_type=SemanticClaimType.BUSINESS_RISK, text=text, direction=ClaimDirection.DECREASE
    )
    verifier = FakeVerifier(response=_dims())

    result = _verify_model_assisted(candidate=candidate, document=doc, verifier=verifier)

    assert verifier.call_count == 0
    assert result.verification_provenance is None
    assert result.verification_version != DETERMINISTIC_FAITHFULNESS_VERSION


def test_model_assisted_call_sets_provenance_without_mutating_extraction_provenance() -> None:
    doc, span = _doc_and_span("海外事業の販売が拡大した可能性がある。", taxonomy_name=_BUSINESS_RISK_TAXONOMY)
    candidate = _candidate(
        evidence_span=span, claim_type=SemanticClaimType.BUSINESS_RISK, text="海外事業の販売が伸びた可能性がある。"
    )
    verifier = FakeVerifier(
        response=_dims(
            ("PROPOSITION_IDENTITY", "PASS", "NO_ISSUE_DETECTED"),
            ("SUBJECT_ATTRIBUTION", "PASS", "NO_ISSUE_DETECTED"),
            ("SCOPE", "PASS", "NO_ISSUE_DETECTED"),
        )
    )
    original_extraction_provenance = candidate.extraction_provenance

    result = _verify_model_assisted(candidate=candidate, document=doc, verifier=verifier)

    assert result.verification_provenance is not None
    assert result.verification_provenance is not candidate.extraction_provenance
    assert candidate.extraction_provenance is original_extraction_provenance


def test_verified_at_remains_utc_and_not_pit_metadata_model_assisted() -> None:
    field_names = set(FaithfulnessVerificationResult.__dataclass_fields__.keys())
    assert "market_public_at" not in field_names
    assert "provider_available_at" not in field_names
    assert "available_at" not in field_names
    assert "verified_at" in field_names


# ============================================================
# D0102.4.2.1 — Model-Assisted Faithfulness Closure Fix
# (D42-F01 / D42-F02 / D42-F03 / D42-N01)
# ============================================================


def _replace_dimension_result(
    results: tuple[FaithfulnessDimensionResult, ...], replacement: FaithfulnessDimensionResult
) -> tuple[FaithfulnessDimensionResult, ...]:
    return tuple(replacement if r.dimension == replacement.dimension else r for r in results)


def _valid_full_accept_result(candidate_reference: str = "CANDREF_x") -> FaithfulnessVerificationResult:
    return FaithfulnessVerificationResult(
        status=FaithfulnessVerificationStatus.SUCCESS,
        overall_outcome=FaithfulnessOutcome.ACCEPT,
        dimension_results=_full_accept_dimension_results(),
        candidate_reference=candidate_reference,
        verification_version=DETERMINISTIC_FAITHFULNESS_VERSION,
        verified_at=_VERIFIED_AT,
    )


# ---- D42-F01: Forged ACCEPT Must Not Promote ----


def test_d42_f01_forged_ambiguous_dimension_with_accept_overall_rejected() -> None:
    valid_result = _valid_full_accept_result()
    forged_dims = _replace_dimension_result(
        valid_result.dimension_results,
        FaithfulnessDimensionResult(
            dimension=FaithfulnessDimension.SCOPE,
            outcome=FaithfulnessDimensionOutcome.AMBIGUOUS,
            reason_code=FaithfulnessReasonCode.SEMANTIC_VERIFICATION_REQUIRED,
            checked_by=FaithfulnessCheckMethod.DETERMINISTIC,
        ),
    )

    with pytest.raises(FaithfulnessSchemaError):
        replace(valid_result, dimension_results=forged_dims)


def test_d42_f01_forged_hard_fail_dimension_with_accept_overall_rejected() -> None:
    valid_result = _valid_full_accept_result()
    forged_dims = _replace_dimension_result(
        valid_result.dimension_results,
        FaithfulnessDimensionResult(
            dimension=FaithfulnessDimension.NEGATION,
            outcome=FaithfulnessDimensionOutcome.FAIL,
            reason_code=FaithfulnessReasonCode.NEGATION_INVERTED,
            checked_by=FaithfulnessCheckMethod.DETERMINISTIC,
        ),
    )

    with pytest.raises(FaithfulnessSchemaError):
        replace(valid_result, dimension_results=forged_dims)


def test_d42_f01_model_dimension_without_provenance_rejected() -> None:
    valid_result = _valid_full_accept_result()
    forged_dims = _replace_dimension_result(
        valid_result.dimension_results,
        FaithfulnessDimensionResult(
            dimension=FaithfulnessDimension.SCOPE,
            outcome=FaithfulnessDimensionOutcome.PASS,
            reason_code=FaithfulnessReasonCode.NO_ISSUE_DETECTED,
            checked_by=FaithfulnessCheckMethod.MODEL,
        ),
    )

    with pytest.raises(FaithfulnessSchemaError):
        replace(valid_result, dimension_results=forged_dims)


def test_d42_f01_zero_model_dimensions_with_provenance_rejected() -> None:
    valid_result = _valid_full_accept_result()

    with pytest.raises(FaithfulnessSchemaError):
        replace(valid_result, verification_provenance=_fake_provenance())


def test_d42_f01_valid_accept_remains_constructible_and_promotable() -> None:
    doc, span = _doc_and_span("業績は堅調に推移した。")
    candidate = _candidate(evidence_span=span, text="業績は堅調に推移した。")
    valid_result = _valid_full_accept_result(candidate_reference=compute_candidate_reference(candidate))

    assert valid_result.status == FaithfulnessVerificationStatus.SUCCESS
    claim = promote_verified_candidate(candidate=candidate, verification_result=valid_result)

    assert claim is not None
    assert claim.faithfulness_outcome == FaithfulnessOutcome.ACCEPT


def test_d42_f01_promotion_rejects_forged_accept_with_ambiguous_dimension() -> None:
    # promote_verified_candidate()自身のDefense in Depth(§2C):
    # Constructor Invariantを迂回した(通常は到達不能な)Objectが渡された
    # としても、Promotion側の独立した再計算が不整合を検出する。
    doc, span = _doc_and_span("業績は堅調に推移した。")
    candidate = _candidate(evidence_span=span, text="業績は堅調に推移した。")
    valid_result = _valid_full_accept_result(candidate_reference=compute_candidate_reference(candidate))
    forged_dims = _replace_dimension_result(
        valid_result.dimension_results,
        FaithfulnessDimensionResult(
            dimension=FaithfulnessDimension.SCOPE,
            outcome=FaithfulnessDimensionOutcome.AMBIGUOUS,
            reason_code=FaithfulnessReasonCode.SEMANTIC_VERIFICATION_REQUIRED,
            checked_by=FaithfulnessCheckMethod.DETERMINISTIC,
        ),
    )
    forged_result = object.__new__(FaithfulnessVerificationResult)
    object.__setattr__(forged_result, "status", FaithfulnessVerificationStatus.SUCCESS)
    object.__setattr__(forged_result, "overall_outcome", FaithfulnessOutcome.ACCEPT)
    object.__setattr__(forged_result, "dimension_results", forged_dims)
    object.__setattr__(forged_result, "candidate_reference", valid_result.candidate_reference)
    object.__setattr__(forged_result, "verification_version", valid_result.verification_version)
    object.__setattr__(forged_result, "verified_at", valid_result.verified_at)
    object.__setattr__(forged_result, "verification_provenance", None)
    object.__setattr__(forged_result, "reason", None)

    with pytest.raises(FaithfulnessSchemaError):
        promote_verified_candidate(candidate=candidate, verification_result=forged_result)


# ---- D42-F02: Deterministic FAIL Is Immutable ----


def test_d42_f02_certainty_deterministic_fail_is_immutable() -> None:
    evidence_text = "損失が生じる可能性がある。販売は堅調である。"
    candidate_text = "損失が生じる。"
    doc, span = _doc_and_span(evidence_text, taxonomy_name=_BUSINESS_RISK_TAXONOMY)
    candidate = _candidate(evidence_span=span, claim_type=SemanticClaimType.BUSINESS_RISK, text=candidate_text)
    verifier = FakeVerifier(
        response=_dims(
            ("PROPOSITION_IDENTITY", "PASS", "NO_ISSUE_DETECTED"),
            ("SUBJECT_ATTRIBUTION", "PASS", "NO_ISSUE_DETECTED"),
            ("SCOPE", "PASS", "NO_ISSUE_DETECTED"),
        )
    )

    result = _verify_model_assisted(candidate=candidate, document=doc, verifier=verifier)

    certainty = _dim_result(result, FaithfulnessDimension.CERTAINTY_AND_COMMITMENT)
    assert certainty.outcome == FaithfulnessDimensionOutcome.FAIL
    assert certainty.checked_by == FaithfulnessCheckMethod.DETERMINISTIC
    assert result.overall_outcome == FaithfulnessOutcome.REJECT


def test_d42_f02_deterministic_fail_dimensions_never_model_requested() -> None:
    cases = [
        (
            "重要な変更はありません。",
            "重要な変更があった。",
            SemanticClaimType.BUSINESS_RISK,
            _BUSINESS_RISK_TAXONOMY,
            ClaimDirection.UNSPECIFIED,
            FaithfulnessDimension.NEGATION,
        ),
        (
            "為替影響は一因である。",
            "為替影響は唯一の原因である。",
            SemanticClaimType.PERFORMANCE_DRIVER,
            "jpcrp_cor:ManagementAnalysisTextBlock",
            ClaimDirection.UNSPECIFIED,
            FaithfulnessDimension.CAUSAL_STRENGTH,
        ),
        (
            "損失が発生する可能性がある。",
            "損失が発生する。",
            SemanticClaimType.BUSINESS_RISK,
            _BUSINESS_RISK_TAXONOMY,
            ClaimDirection.UNSPECIFIED,
            FaithfulnessDimension.CERTAINTY_AND_COMMITMENT,
        ),
        (
            "業績は堅調に推移した。",
            "業績は4.0%増加した。",
            SemanticClaimType.PERFORMANCE_CHANGE,
            "jpcrp_cor:ManagementAnalysisTextBlock",
            ClaimDirection.UNSPECIFIED,
            FaithfulnessDimension.QUANTITY,
        ),
        (
            "当中間連結会計期間の業績は堅調であった。",
            "今後も継続的に堅調である。",
            SemanticClaimType.OUTLOOK,
            "jpcrp_cor:ManagementAnalysisTextBlock",
            ClaimDirection.UNSPECIFIED,
            FaithfulnessDimension.TEMPORAL_SCOPE,
        ),
        (
            "リスクは増加した。",
            "リスクは増加した。",
            SemanticClaimType.BUSINESS_RISK,
            _BUSINESS_RISK_TAXONOMY,
            ClaimDirection.DECREASE,
            FaithfulnessDimension.PROPOSITION_IDENTITY,
        ),
    ]
    for evidence_text, candidate_text, claim_type, taxonomy, direction, expected_fail_dim in cases:
        doc, span = _doc_and_span(evidence_text, taxonomy_name=taxonomy)
        candidate = _candidate(evidence_span=span, claim_type=claim_type, text=candidate_text, direction=direction)
        deterministic_results = _run_all_dimension_checks(evidence_text=evidence_text, candidate=candidate)
        by_dim = {r.dimension: r for r in deterministic_results}
        assert by_dim[expected_fail_dim].outcome == FaithfulnessDimensionOutcome.FAIL, (evidence_text, candidate_text)

        required = _determine_model_required_dimensions(deterministic_results, evidence_text=evidence_text, candidate=candidate)

        assert expected_fail_dim not in required, (evidence_text, candidate_text, required)
        # 一般化した不変条件: いかなるシナリオでも、Deterministic FAILの
        # 軸がModel-Required集合に含まれることは絶対に無い。
        for dimension, result in by_dim.items():
            if result.outcome == FaithfulnessDimensionOutcome.FAIL:
                assert dimension not in required, (evidence_text, candidate_text, dimension, required)


# ---- D42-F03: Required Dimension MODEL NOT_APPLICABLE ----


def test_d42_f03_required_dimension_model_not_applicable_does_not_crash() -> None:
    text = "リスクについて記載する。"
    doc, span = _doc_and_span(text, taxonomy_name=_BUSINESS_RISK_TAXONOMY)
    candidate = _candidate(evidence_span=span, claim_type=SemanticClaimType.BUSINESS_RISK, text=text)
    verifier = FakeVerifier(response=_dims(("CERTAINTY_AND_COMMITMENT", "NOT_APPLICABLE", "NOT_APPLICABLE_NO_RELEVANT_CONTENT")))

    result = _verify_model_assisted(candidate=candidate, document=doc, verifier=verifier)

    assert result.status == FaithfulnessVerificationStatus.SUCCESS
    certainty = _dim_result(result, FaithfulnessDimension.CERTAINTY_AND_COMMITMENT)
    assert certainty.outcome == FaithfulnessDimensionOutcome.AMBIGUOUS
    assert certainty.checked_by == FaithfulnessCheckMethod.MODEL
    assert result.verification_provenance is not None
    assert result.overall_outcome == FaithfulnessOutcome.REVIEW_REQUIRED


def test_d42_f03_multiple_model_dimensions_mixed_override_and_pass() -> None:
    evidence_text = "リスクについて説明する。"
    candidate_text = "リスクについて解説する。"
    doc, span = _doc_and_span(evidence_text)
    candidate = _candidate(evidence_span=span, claim_type=SemanticClaimType.MANAGEMENT_EXPLANATION, text=candidate_text)
    verifier = FakeVerifier(
        response=_dims(
            ("PROPOSITION_IDENTITY", "AMBIGUOUS", "SEMANTIC_VERIFICATION_REQUIRED"),
            ("SUBJECT_ATTRIBUTION", "PASS", "NO_ISSUE_DETECTED"),
            ("SCOPE", "PASS", "NO_ISSUE_DETECTED"),
            ("CERTAINTY_AND_COMMITMENT", "NOT_APPLICABLE", "NOT_APPLICABLE_NO_RELEVANT_CONTENT"),
        )
    )

    result = _verify_model_assisted(candidate=candidate, document=doc, verifier=verifier)

    assert result.status == FaithfulnessVerificationStatus.SUCCESS
    subject = _dim_result(result, FaithfulnessDimension.SUBJECT_ATTRIBUTION)
    assert subject.outcome == FaithfulnessDimensionOutcome.PASS
    assert subject.checked_by == FaithfulnessCheckMethod.MODEL
    certainty = _dim_result(result, FaithfulnessDimension.CERTAINTY_AND_COMMITMENT)
    assert certainty.outcome == FaithfulnessDimensionOutcome.AMBIGUOUS
    assert certainty.checked_by == FaithfulnessCheckMethod.MODEL
    assert result.verification_provenance is not None
    assert result.overall_outcome == FaithfulnessOutcome.REVIEW_REQUIRED


# ---- D42-N01: Dimension / Outcome / Reason Compatibility ----


def test_n01_subject_attribution_pass_with_quantity_invented_rejected() -> None:
    with pytest.raises(FaithfulnessSchemaError):
        FaithfulnessDimensionResult(
            dimension=FaithfulnessDimension.SUBJECT_ATTRIBUTION,
            outcome=FaithfulnessDimensionOutcome.PASS,
            reason_code=FaithfulnessReasonCode.QUANTITY_INVENTED,
            checked_by=FaithfulnessCheckMethod.DETERMINISTIC,
        )


def test_n01_quantity_pass_with_negation_inverted_rejected() -> None:
    with pytest.raises(FaithfulnessSchemaError):
        FaithfulnessDimensionResult(
            dimension=FaithfulnessDimension.QUANTITY,
            outcome=FaithfulnessDimensionOutcome.PASS,
            reason_code=FaithfulnessReasonCode.NEGATION_INVERTED,
            checked_by=FaithfulnessCheckMethod.DETERMINISTIC,
        )


def test_n01_scope_not_applicable_with_direction_mismatch_rejected() -> None:
    with pytest.raises(FaithfulnessSchemaError):
        FaithfulnessDimensionResult(
            dimension=FaithfulnessDimension.SCOPE,
            outcome=FaithfulnessDimensionOutcome.NOT_APPLICABLE,
            reason_code=FaithfulnessReasonCode.DIRECTION_MISMATCH_DETECTED,
            checked_by=FaithfulnessCheckMethod.DETERMINISTIC,
        )


def test_n01_positive_control_proposition_identity_pass_no_issue_detected() -> None:
    result = FaithfulnessDimensionResult(
        dimension=FaithfulnessDimension.PROPOSITION_IDENTITY,
        outcome=FaithfulnessDimensionOutcome.PASS,
        reason_code=FaithfulnessReasonCode.NO_ISSUE_DETECTED,
        checked_by=FaithfulnessCheckMethod.DETERMINISTIC,
    )
    assert result.outcome == FaithfulnessDimensionOutcome.PASS


def test_n01_positive_control_scope_ambiguous_semantic_verification_required() -> None:
    result = FaithfulnessDimensionResult(
        dimension=FaithfulnessDimension.SCOPE,
        outcome=FaithfulnessDimensionOutcome.AMBIGUOUS,
        reason_code=FaithfulnessReasonCode.SEMANTIC_VERIFICATION_REQUIRED,
        checked_by=FaithfulnessCheckMethod.DETERMINISTIC,
    )
    assert result.outcome == FaithfulnessDimensionOutcome.AMBIGUOUS


def test_n01_positive_control_quantity_fail_quantity_invented() -> None:
    result = FaithfulnessDimensionResult(
        dimension=FaithfulnessDimension.QUANTITY,
        outcome=FaithfulnessDimensionOutcome.FAIL,
        reason_code=FaithfulnessReasonCode.QUANTITY_INVENTED,
        checked_by=FaithfulnessCheckMethod.DETERMINISTIC,
    )
    assert result.outcome == FaithfulnessDimensionOutcome.FAIL


def test_n01_contract_impossible_combination_is_violation_not_exception() -> None:
    result = _run_with_raw_response(
        {
            "dimensions": [
                {"dimension": "SUBJECT_ATTRIBUTION", "outcome": "PASS", "reason_code": "QUANTITY_INVENTED"},
                {"dimension": "PROPOSITION_IDENTITY", "outcome": "PASS", "reason_code": "NO_ISSUE_DETECTED"},
                {"dimension": "SCOPE", "outcome": "PASS", "reason_code": "NO_ISSUE_DETECTED"},
            ]
        }
    )
    assert result.status == FaithfulnessVerificationStatus.VERIFIER_CONTRACT_VIOLATION
    assert result.overall_outcome is None
