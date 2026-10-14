"""`lib.disclosures.evidence_integration`(D0103、DEV-AUTO-02.1.1 Pilot)の
Regression Test。

SemanticClaim -> Evidence Integrationの唯一の公開Entrypoint
(`integrate_accepted_semantic_claim()`)が、以下を機械的に強制することを
検証する:

1. `FaithfulnessOutcome.ACCEPT`のSemanticClaimのみが`EvidenceRecord`へ
   昇格し、`REVIEW_REQUIRED`は一切昇格しない(ACCEPT-only Gate)。
2. `claim.evidence_span.document_id`と`document.internal_document_id`の
   取り違えをFail Closedで検知する。
3. Provenance(`ai_derived_provenance`)・PIT Timestamp優先順位
   (D0049/D0050、`market_public_at`へは決してFallbackしない)を書き換え
   ずに転記する。

Fixture方式は`test_disclosures_semantic_claims.py`と同じ(Synthetic
EDINET-shaped ZIPを構築し、実際の`normalize_edinet_type1_zip()`経由で
D0101.1の実`EvidenceSpan`を得る)。
"""

from __future__ import annotations

import io
import zipfile
from datetime import UTC, datetime

import pytest
from lib.disclosures.evidence_integration import (
    EvidenceIntegrationSchemaError,
    SemanticClaimEvidenceIntegrationResult,
    SemanticClaimIntegrationStatus,
    integrate_accepted_semantic_claim,
)
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
from lib.evidence.model import AiDerivedProvenance, AvailabilityBasis, DataLayer, EvidenceRecord, EvidenceType
from lib.sources.catalog import DataCapability, PrimaryOrSecondary, SourceAuthorityClass

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


def _provenance() -> AiDerivedProvenance:
    return AiDerivedProvenance(
        model_provider="test-provider",
        model_name="test-model",
        model_version="v1",
        generated_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


def _claim(
    *,
    evidence_span: EvidenceSpan,
    faithfulness_outcome: FaithfulnessOutcome = FaithfulnessOutcome.ACCEPT,
    claim_type: SemanticClaimType = SemanticClaimType.BUSINESS_RISK,
    normalized_claim_text: str = "重要な変更はありません。",
    direction: ClaimDirection = ClaimDirection.UNSPECIFIED,
) -> SemanticClaim:
    return build_semantic_claim(
        claim_type=claim_type,
        normalized_claim_text=normalized_claim_text,
        direction=direction,
        evidence_span=evidence_span,
        faithfulness_outcome=faithfulness_outcome,
        extraction_version="EXTRACT_V1",
        extraction_provenance=_provenance(),
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
) -> DisclosureDocument:
    return DisclosureDocument(
        internal_document_id=internal_document_id,
        source_document_id="S1",
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


# --- 1: ACCEPT-only Gate -----------------------------------------------------


def test_accepted_claim_is_integrated_into_evidence_record() -> None:
    doc = _single_member_doc(_ix("jpcrp_cor:BusinessRisksTextBlock", "重要な変更はありません。"))
    claim = _claim(evidence_span=_span_for(doc), faithfulness_outcome=FaithfulnessOutcome.ACCEPT)
    document = _disclosure_document()

    result = integrate_accepted_semantic_claim(
        claim=claim, document=document, source_authority_class=SourceAuthorityClass.PRIMARY_OFFICIAL
    )

    assert result.status == SemanticClaimIntegrationStatus.SUCCESS
    assert result.reason is None
    assert isinstance(result.evidence, EvidenceRecord)
    evidence = result.evidence
    assert evidence.evidence_id == f"EVID_CLAIM_{claim.claim_id}"
    assert evidence.evidence_type == EvidenceType.CLAIM
    assert evidence.layer == DataLayer.DERIVED
    assert evidence.capability == DataCapability.DISCLOSURE
    assert claim.normalized_claim_text in evidence.content
    assert claim.claim_type.value in evidence.content
    assert claim.direction.value in evidence.content
    assert evidence.related_codes == ("7203",)
    assert evidence.ai_derived_provenance == claim.extraction_provenance
    assert evidence.source.source_authority_class == SourceAuthorityClass.PRIMARY_OFFICIAL
    assert evidence.source.primary_or_secondary == PrimaryOrSecondary.PRIMARY


def test_review_required_claim_is_not_integrated() -> None:
    doc = _single_member_doc(_ix("jpcrp_cor:BusinessRisksTextBlock", "重要な変更はありません。"))
    claim = _claim(evidence_span=_span_for(doc), faithfulness_outcome=FaithfulnessOutcome.REVIEW_REQUIRED)
    document = _disclosure_document()

    result = integrate_accepted_semantic_claim(
        claim=claim, document=document, source_authority_class=SourceAuthorityClass.PRIMARY_OFFICIAL
    )

    assert result.status == SemanticClaimIntegrationStatus.NOT_ACCEPTED
    assert result.evidence is None
    assert result.reason is not None
    assert "REVIEW_REQUIRED" in result.reason


# --- 2: Document Identity Join Gate ------------------------------------------


def test_document_identity_mismatch_is_detected() -> None:
    doc = _single_member_doc(_ix("jpcrp_cor:BusinessRisksTextBlock", "重要な変更はありません。"), document_id="DOC_REAL")
    claim = _claim(evidence_span=_span_for(doc), faithfulness_outcome=FaithfulnessOutcome.ACCEPT)
    wrong_document = _disclosure_document(internal_document_id="DOC_WRONG")

    result = integrate_accepted_semantic_claim(
        claim=claim, document=wrong_document, source_authority_class=SourceAuthorityClass.PRIMARY_OFFICIAL
    )

    assert result.status == SemanticClaimIntegrationStatus.DOCUMENT_IDENTITY_MISMATCH
    assert result.evidence is None
    assert result.reason is not None
    assert "DOC_REAL" in result.reason
    assert "DOC_WRONG" in result.reason


# --- 3: PIT Timestamp Policy(D0049/D0050をそのまま踏襲) ---------------------


def test_available_at_never_falls_back_to_market_public_at_when_provider_available_at_unknown() -> None:
    doc = _single_member_doc(_ix("jpcrp_cor:BusinessRisksTextBlock", "重要な変更はありません。"))
    claim = _claim(evidence_span=_span_for(doc), faithfulness_outcome=FaithfulnessOutcome.ACCEPT)
    market_public_at = datetime(2026, 8, 17, 15, 0, tzinfo=UTC)
    retrieved_at = datetime(2026, 8, 17, 15, 6, tzinfo=UTC)
    document = _disclosure_document(market_public_at=market_public_at, retrieved_at=retrieved_at)

    result = integrate_accepted_semantic_claim(
        claim=claim, document=document, source_authority_class=SourceAuthorityClass.PRIMARY_OFFICIAL
    )

    assert result.evidence is not None
    assert result.evidence.source.published_at == market_public_at
    assert result.evidence.source.available_at == retrieved_at
    assert result.evidence.source.available_at != market_public_at


def test_available_at_uses_confirmed_provider_available_at_when_basis_is_not_unknown() -> None:
    doc = _single_member_doc(_ix("jpcrp_cor:BusinessRisksTextBlock", "重要な変更はありません。"))
    claim = _claim(evidence_span=_span_for(doc), faithfulness_outcome=FaithfulnessOutcome.ACCEPT)
    provider_available_at = datetime(2026, 8, 17, 15, 2, tzinfo=UTC)
    retrieved_at = datetime(2026, 8, 17, 15, 6, tzinfo=UTC)
    document = _disclosure_document(
        provider_available_at=provider_available_at,
        provider_available_at_basis=AvailabilityBasis.EXACT,
        retrieved_at=retrieved_at,
    )

    result = integrate_accepted_semantic_claim(
        claim=claim, document=document, source_authority_class=SourceAuthorityClass.PRIMARY_OFFICIAL
    )

    assert result.evidence is not None
    assert result.evidence.source.available_at == provider_available_at
    assert result.evidence.source.available_at != retrieved_at


# --- 4: Related Codes / Entity Join ------------------------------------------


def test_related_codes_empty_when_entity_id_is_none() -> None:
    doc = _single_member_doc(_ix("jpcrp_cor:BusinessRisksTextBlock", "重要な変更はありません。"))
    claim = _claim(evidence_span=_span_for(doc), faithfulness_outcome=FaithfulnessOutcome.ACCEPT)
    document = _disclosure_document(entity_id=None)

    result = integrate_accepted_semantic_claim(
        claim=claim, document=document, source_authority_class=SourceAuthorityClass.PRIMARY_OFFICIAL
    )

    assert result.evidence is not None
    assert result.evidence.related_codes == ()


# --- 5: Claim Integrity Gate --------------------------------------------------


def test_non_semantic_claim_raises_schema_error() -> None:
    document = _disclosure_document()
    with pytest.raises(EvidenceIntegrationSchemaError):
        integrate_accepted_semantic_claim(
            claim="not-a-semantic-claim",  # type: ignore[arg-type]
            document=document,
            source_authority_class=SourceAuthorityClass.PRIMARY_OFFICIAL,
        )


# --- 6: Result Invariants (Typed Outcome, no Forged/Inconsistent States) ----


def test_result_rejects_success_without_evidence() -> None:
    with pytest.raises(EvidenceIntegrationSchemaError):
        SemanticClaimEvidenceIntegrationResult(status=SemanticClaimIntegrationStatus.SUCCESS, evidence=None)


def test_result_rejects_non_success_with_evidence() -> None:
    doc = _single_member_doc(_ix("jpcrp_cor:BusinessRisksTextBlock", "重要な変更はありません。"))
    claim = _claim(evidence_span=_span_for(doc), faithfulness_outcome=FaithfulnessOutcome.ACCEPT)
    document = _disclosure_document()
    success_result = integrate_accepted_semantic_claim(
        claim=claim, document=document, source_authority_class=SourceAuthorityClass.PRIMARY_OFFICIAL
    )
    assert success_result.evidence is not None

    with pytest.raises(EvidenceIntegrationSchemaError):
        SemanticClaimEvidenceIntegrationResult(
            status=SemanticClaimIntegrationStatus.NOT_ACCEPTED, evidence=success_result.evidence
        )


# --- 7: Forged / Structurally Invalid Input (Fail Closed) ---------------------


def test_raw_string_accept_outcome_is_not_integrated() -> None:
    doc = _single_member_doc(_ix("jpcrp_cor:BusinessRisksTextBlock", "重要な変更はありません。"))
    claim = _claim(evidence_span=_span_for(doc), faithfulness_outcome=FaithfulnessOutcome.ACCEPT)
    # StrEnumは生の文字列と`==`で一致するため、`__post_init__`を迂回した
    # 文字列"ACCEPT"がACCEPT-only Gateを通過しないことを確認する。
    object.__setattr__(claim, "faithfulness_outcome", "ACCEPT")

    with pytest.raises(EvidenceIntegrationSchemaError):
        integrate_accepted_semantic_claim(
            claim=claim, document=_disclosure_document(), source_authority_class=SourceAuthorityClass.PRIMARY_OFFICIAL
        )


def test_forged_accept_on_review_required_claim_is_rejected() -> None:
    doc = _single_member_doc(_ix("jpcrp_cor:BusinessRisksTextBlock", "重要な変更はありません。"))
    claim = _claim(evidence_span=_span_for(doc), faithfulness_outcome=FaithfulnessOutcome.REVIEW_REQUIRED)
    # `faithfulness_review_required=True`のまま、Outcomeだけを後から
    # ACCEPTへ書き換えたForged State。
    object.__setattr__(claim, "faithfulness_outcome", FaithfulnessOutcome.ACCEPT)

    with pytest.raises(EvidenceIntegrationSchemaError):
        integrate_accepted_semantic_claim(
            claim=claim, document=_disclosure_document(), source_authority_class=SourceAuthorityClass.PRIMARY_OFFICIAL
        )


def test_non_disclosure_document_raises_schema_error() -> None:
    doc = _single_member_doc(_ix("jpcrp_cor:BusinessRisksTextBlock", "重要な変更はありません。"))
    claim = _claim(evidence_span=_span_for(doc), faithfulness_outcome=FaithfulnessOutcome.ACCEPT)

    # `NormalizedDisclosureDocument`はPIT Timestampを持たない別Objectであり、
    # `DisclosureDocument`の代わりに渡された場合は拒否する。
    with pytest.raises(EvidenceIntegrationSchemaError):
        integrate_accepted_semantic_claim(
            claim=claim,
            document=doc,  # type: ignore[arg-type]
            source_authority_class=SourceAuthorityClass.PRIMARY_OFFICIAL,
        )


def test_non_source_authority_class_raises_schema_error() -> None:
    doc = _single_member_doc(_ix("jpcrp_cor:BusinessRisksTextBlock", "重要な変更はありません。"))
    claim = _claim(evidence_span=_span_for(doc), faithfulness_outcome=FaithfulnessOutcome.ACCEPT)

    with pytest.raises(EvidenceIntegrationSchemaError):
        integrate_accepted_semantic_claim(
            claim=claim,
            document=_disclosure_document(),
            source_authority_class="PRIMARY_OFFICIAL",  # type: ignore[arg-type]
        )


# --- 8: Provenance Preservation ----------------------------------------------


def test_provenance_and_span_locator_are_preserved_verbatim() -> None:
    doc = _single_member_doc(_ix("jpcrp_cor:BusinessRisksTextBlock", "重要な変更はありません。"))
    span = _span_for(doc)
    claim = _claim(evidence_span=span, faithfulness_outcome=FaithfulnessOutcome.ACCEPT)
    document = _disclosure_document(provenance_id="PROV_1")

    result = integrate_accepted_semantic_claim(
        claim=claim, document=document, source_authority_class=SourceAuthorityClass.PRIMARY_OFFICIAL
    )

    assert result.evidence is not None
    evidence = result.evidence
    assert evidence.ai_derived_provenance is claim.extraction_provenance
    assert evidence.provenance_id == "PROV_1"
    assert evidence.source.provenance_id == "PROV_1"
    assert evidence.source.source_id == claim.claim_id
    assert evidence.source.source_type == "DISCLOSURE_SEMANTIC_CLAIM"
    assert evidence.source.originating_source == "EDINET"
    assert evidence.source.delivery_provider == "EDINET"
    assert evidence.source.retrieved_at == document.retrieved_at
    assert f"source_document={document.internal_document_id}" in evidence.content
    assert f"member_path={span.member_path}" in evidence.content
    assert f"taxonomy_element_name={span.taxonomy_element_name}" in evidence.content
    assert f"occurrence_index={span.occurrence_index}" in evidence.content
    assert f"char_start={span.char_start}, char_end={span.char_end}" in evidence.content
    assert f"source_raw_canonical_content_hash={span.source_raw_canonical_content_hash}" in evidence.content
    assert f"source_normalizer_version={span.source_normalizer_version}" in evidence.content
    assert f"extraction_version={claim.extraction_version}" in evidence.content


def test_integration_is_deterministic_and_does_not_mutate_claim() -> None:
    doc = _single_member_doc(_ix("jpcrp_cor:BusinessRisksTextBlock", "重要な変更はありません。"))
    span = _span_for(doc)
    claim = _claim(evidence_span=span, faithfulness_outcome=FaithfulnessOutcome.ACCEPT)
    expected_claim = _claim(evidence_span=span, faithfulness_outcome=FaithfulnessOutcome.ACCEPT)
    document = _disclosure_document()

    first = integrate_accepted_semantic_claim(
        claim=claim, document=document, source_authority_class=SourceAuthorityClass.PRIMARY_OFFICIAL
    )
    second = integrate_accepted_semantic_claim(
        claim=claim, document=document, source_authority_class=SourceAuthorityClass.PRIMARY_OFFICIAL
    )

    assert first == second
    assert claim == expected_claim


# --- 9: Relation Semantics(Investment Polarityへ変換しない) ------------------


def test_descriptive_direction_is_transcribed_without_investment_polarity_or_relation() -> None:
    doc = _single_member_doc(_ix("jpcrp_cor:BusinessRisksTextBlock", "重要な変更はありません。"))
    claim = _claim(
        evidence_span=_span_for(doc),
        faithfulness_outcome=FaithfulnessOutcome.ACCEPT,
        claim_type=SemanticClaimType.PERFORMANCE_CHANGE,
        normalized_claim_text="売上高は増加しました。",
        direction=ClaimDirection.INCREASE,
    )

    result = integrate_accepted_semantic_claim(
        claim=claim, document=_disclosure_document(), source_authority_class=SourceAuthorityClass.PRIMARY_OFFICIAL
    )

    assert result.evidence is not None
    evidence = result.evidence
    assert "claim_type=PERFORMANCE_CHANGE" in evidence.content
    assert "direction=INCREASE" in evidence.content
    # FACTへ昇格しない(本文の主張内容の真偽は検証していない)。
    assert evidence.evidence_type == EvidenceType.CLAIM
    # `EvidenceRelation`(SUPPORTS/CONTRADICTS等)・売買判断語はこのBoundaryでは付与しない。
    for forbidden in ("SUPPORTS", "CONTRADICTS", "BUY", "SELL", "BULLISH", "BEARISH"):
        assert forbidden not in evidence.content
    assert not hasattr(evidence, "relation")


# --- 10: PIT Usability(`is_usable_at()`経由でのLeakage確認) -----------------


def test_evidence_is_not_usable_between_market_public_at_and_retrieved_at() -> None:
    doc = _single_member_doc(_ix("jpcrp_cor:BusinessRisksTextBlock", "重要な変更はありません。"))
    claim = _claim(evidence_span=_span_for(doc), faithfulness_outcome=FaithfulnessOutcome.ACCEPT)
    market_public_at = datetime(2026, 8, 17, 15, 0, tzinfo=UTC)
    retrieved_at = datetime(2026, 8, 17, 15, 6, tzinfo=UTC)
    document = _disclosure_document(market_public_at=market_public_at, retrieved_at=retrieved_at)

    result = integrate_accepted_semantic_claim(
        claim=claim, document=document, source_authority_class=SourceAuthorityClass.PRIMARY_OFFICIAL
    )

    assert result.evidence is not None
    assert not result.evidence.is_usable_at(datetime(2026, 8, 17, 15, 3, tzinfo=UTC))
    assert result.evidence.is_usable_at(retrieved_at)


def test_provider_available_at_with_unknown_basis_is_not_used() -> None:
    doc = _single_member_doc(_ix("jpcrp_cor:BusinessRisksTextBlock", "重要な変更はありません。"))
    claim = _claim(evidence_span=_span_for(doc), faithfulness_outcome=FaithfulnessOutcome.ACCEPT)
    retrieved_at = datetime(2026, 8, 17, 15, 6, tzinfo=UTC)
    document = _disclosure_document(
        provider_available_at=datetime(2026, 8, 17, 15, 2, tzinfo=UTC),
        provider_available_at_basis=AvailabilityBasis.UNKNOWN,
        retrieved_at=retrieved_at,
    )

    result = integrate_accepted_semantic_claim(
        claim=claim, document=document, source_authority_class=SourceAuthorityClass.PRIMARY_OFFICIAL
    )

    assert result.evidence is not None
    assert result.evidence.source.available_at == retrieved_at


def test_extraction_generated_at_is_not_used_as_availability() -> None:
    doc = _single_member_doc(_ix("jpcrp_cor:BusinessRisksTextBlock", "重要な変更はありません。"))
    claim = _claim(evidence_span=_span_for(doc), faithfulness_outcome=FaithfulnessOutcome.ACCEPT)
    assert claim.extraction_provenance is not None
    retrieved_at = datetime(2026, 8, 17, 15, 6, tzinfo=UTC)
    document = _disclosure_document(retrieved_at=retrieved_at)

    result = integrate_accepted_semantic_claim(
        claim=claim, document=document, source_authority_class=SourceAuthorityClass.PRIMARY_OFFICIAL
    )

    assert result.evidence is not None
    assert result.evidence.source.available_at == retrieved_at
    assert result.evidence.source.available_at != claim.extraction_provenance.generated_at
    assert result.evidence.source.published_at is None
