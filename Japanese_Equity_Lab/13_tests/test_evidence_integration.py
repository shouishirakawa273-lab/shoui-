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
