"""`lib.disclosures.semantic_claims`(Stage 3.18.4、D0102.2)のRegression Test。

D0102.1(DECISIONS.md)で確定したDeterministic Schema Contractを、最小の
Synthetic Fixtureで固定する。LLM/Faithfulness Verification Algorithm
はいずれも本Moduleに存在しないため、それらのTestは含まない
(D0102.2 §16「NO FAITHFULNESS IMPLEMENTATION YET」)。

Fixture方式は`test_disclosures_normalization.py`と同じ
(Synthetic EDINET-shaped ZIPを構築し、実際の`normalize_edinet_type1_
zip()`経由でD0101.1の実Objectを得る)——D0102.2独自のFake Objectを
作らないことで、D0101.1の実際の挙動との整合性をそのままTest対象にする。
"""

from __future__ import annotations

import io
import zipfile
from datetime import UTC, datetime

import pytest
from lib.disclosures.normalization import NormalizedDisclosureDocument, normalize_edinet_type1_zip
from lib.disclosures.semantic_claims import (
    ClaimDirection,
    EvidenceSpan,
    FaithfulnessOutcome,
    RevalidationResult,
    SemanticClaim,
    SemanticClaimSchemaError,
    SemanticClaimType,
    build_semantic_claim,
    compute_claim_id,
    compute_semantic_identity_key,
    revalidate_evidence_span,
)
from lib.evidence.model import AiDerivedProvenance

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
_RISK_PATH = "XBRL/PublicDoc/0102010_honbun_test_ixbrl.htm"


def _normalize(raw_zip: bytes, *, document_id: str = "DOC1") -> NormalizedDisclosureDocument:
    return normalize_edinet_type1_zip(document_id=document_id, raw_zip_bytes=raw_zip)


def _single_member_doc(body_inner: str, *, document_id: str = "DOC1") -> NormalizedDisclosureDocument:
    raw_zip = _build_zip({_BODY_PATH: _htm(body_inner)})
    return _normalize(raw_zip, document_id=document_id)


def _provenance() -> AiDerivedProvenance:
    return AiDerivedProvenance(
        model_provider="test-provider",
        model_name="test-model",
        model_version="v1",
        generated_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


# --- 1: EvidenceSpan Factoryが正確にTextBlock Provenanceをcopyする ------------


def test_evidence_span_factory_copies_exact_text_block_provenance() -> None:
    doc = _single_member_doc(_ix("jpcrp_cor:BusinessRisksTextBlock", "重要な変更はありません。"))
    member = doc.members[0]
    text_block = member.text_blocks[0]

    span = EvidenceSpan.from_text_block(document=doc, member=member, text_block=text_block)

    assert span.document_id == doc.document_id
    assert span.source_raw_canonical_content_hash == doc.raw_canonical_content_hash
    assert span.source_normalizer_version == doc.normalizer_version
    assert span.member_path == member.member_path
    assert span.taxonomy_element_name == text_block.taxonomy_element_name
    assert span.occurrence_index == text_block.occurrence_index
    assert span.char_start == text_block.char_start
    assert span.char_end == text_block.char_end
    assert span.supporting_quote == text_block.normalized_text


# --- 2: supporting_quote Exact-Slice Invariant --------------------------------


def test_supporting_quote_exact_slice_invariant() -> None:
    doc = _single_member_doc(_ix("jpcrp_cor:X", "テスト内容です。"))
    member = doc.members[0]
    span = EvidenceSpan.from_text_block(document=doc, member=member, text_block=member.text_blocks[0])

    assert member.normalized_text[span.char_start : span.char_end] == span.supporting_quote


# --- 3: 異なる2 TextBlock内の同一Proseは別々のEvidence Identityになる ---------


def test_identical_prose_in_two_text_blocks_produces_distinct_evidence_identity() -> None:
    # 同一Taxonomy要素名を2回使うことで、occurrence_indexによる
    # Disambiguationが実際に機能することを確認する(D0101.1の既存挙動)。
    body = _ix("jpcrp_cor:NoteA", "同文") + _ix("jpcrp_cor:NoteA", "同文")
    doc = _single_member_doc(body)
    member = doc.members[0]
    assert len(member.text_blocks) == 2

    span_a = EvidenceSpan.from_text_block(document=doc, member=member, text_block=member.text_blocks[0])
    span_b = EvidenceSpan.from_text_block(document=doc, member=member, text_block=member.text_blocks[1])

    assert span_a.supporting_quote == span_b.supporting_quote
    assert span_a.taxonomy_element_name == span_b.taxonomy_element_name
    assert span_a.occurrence_index != span_b.occurrence_index
    assert (span_a.char_start, span_a.char_end) != (span_b.char_start, span_b.char_end)


# --- 4: MD&A/Riskで同一文言でもProvenanceは別のまま ----------------------------


def test_identical_quote_in_mda_and_risk_remains_distinct() -> None:
    raw_zip = _build_zip(
        {
            _BODY_PATH: _htm(_ix("jpcrp_cor:ManagementAnalysisTextBlock", "重要な変更はありません。")),
            _RISK_PATH: _htm(_ix("jpcrp_cor:BusinessRisksTextBlock", "重要な変更はありません。")),
        }
    )
    doc = _normalize(raw_zip)
    members_by_path = {m.member_path: m for m in doc.members}
    mda_member = members_by_path[_BODY_PATH]
    risk_member = members_by_path[_RISK_PATH]

    mda_span = EvidenceSpan.from_text_block(document=doc, member=mda_member, text_block=mda_member.text_blocks[0])
    risk_span = EvidenceSpan.from_text_block(document=doc, member=risk_member, text_block=risk_member.text_blocks[0])

    assert mda_span.supporting_quote == risk_span.supporting_quote
    assert mda_span.taxonomy_element_name != risk_span.taxonomy_element_name
    assert mda_span.member_path != risk_span.member_path


# --- 5/6: EvidenceSpan <-> SemanticClaim Cardinality ---------------------------


def _build_claim(
    span: EvidenceSpan,
    *,
    claim_type: SemanticClaimType = SemanticClaimType.BUSINESS_RISK,
    text: str = "重要な変更はありません。",
    extraction_version: str = "EXTRACT_V1",
    outcome: FaithfulnessOutcome = FaithfulnessOutcome.ACCEPT,
) -> SemanticClaim:
    return build_semantic_claim(
        claim_type=claim_type,
        normalized_claim_text=text,
        direction=ClaimDirection.UNSPECIFIED,
        evidence_span=span,
        faithfulness_outcome=outcome,
        extraction_version=extraction_version,
        extraction_provenance=_provenance(),
    )


def test_one_evidence_span_can_be_used_by_multiple_semantic_claims() -> None:
    doc = _single_member_doc(_ix("jpcrp_cor:BusinessRisksTextBlock", "重要な変更はありません。"))
    member = doc.members[0]
    span = EvidenceSpan.from_text_block(document=doc, member=member, text_block=member.text_blocks[0])

    claim_a = _build_claim(span, claim_type=SemanticClaimType.BUSINESS_RISK, text="claim A")
    claim_b = _build_claim(span, claim_type=SemanticClaimType.MANAGEMENT_EXPLANATION, text="claim B")

    assert claim_a.evidence_span == span
    assert claim_b.evidence_span == span
    assert claim_a.claim_id != claim_b.claim_id


def test_semantic_claim_cannot_contain_multiple_evidence_spans() -> None:
    doc = _single_member_doc(_ix("jpcrp_cor:X", "内容"))
    member = doc.members[0]
    span = EvidenceSpan.from_text_block(document=doc, member=member, text_block=member.text_blocks[0])

    with pytest.raises(SemanticClaimSchemaError):
        SemanticClaim(
            claim_id="CLAIM_dummy",
            semantic_identity_key="SEMID_dummy",
            claim_type=SemanticClaimType.BUSINESS_RISK,
            normalized_claim_text="text",
            direction=ClaimDirection.UNSPECIFIED,
            evidence_span=(span, span),  # type: ignore[arg-type]
            faithfulness_outcome=FaithfulnessOutcome.ACCEPT,
            faithfulness_review_required=False,
            extraction_version="EXTRACT_V1",
        )


# --- 7/8: Taxonomy Enum ---------------------------------------------------------


@pytest.mark.parametrize(
    "claim_type",
    [
        SemanticClaimType.PERFORMANCE_CHANGE,
        SemanticClaimType.PERFORMANCE_DRIVER,
        SemanticClaimType.BUSINESS_RISK,
        SemanticClaimType.MANAGEMENT_EXPLANATION,
        SemanticClaimType.OUTLOOK,
        SemanticClaimType.CAPITAL_ALLOCATION,
    ],
)
def test_all_six_approved_claim_types_accepted(claim_type: SemanticClaimType) -> None:
    doc = _single_member_doc(_ix("jpcrp_cor:X", "内容"))
    member = doc.members[0]
    span = EvidenceSpan.from_text_block(document=doc, member=member, text_block=member.text_blocks[0])
    claim = _build_claim(span, claim_type=claim_type)
    assert claim.claim_type == claim_type


def test_forbidden_catch_all_type_impossible_through_closed_enum() -> None:
    forbidden_names = [
        "OTHER_MATERIAL_DISCLOSURE",
        "BULLISH",
        "BEARISH",
        "POSITIVE_CATALYST",
        "NEGATIVE_CATALYST",
        "ATTRACTIVE_VALUATION",
        "COMPETITIVE_ADVANTAGE",
        "GOOD_MANAGEMENT",
        "BAD_MANAGEMENT",
    ]
    valid_names = {member.name for member in SemanticClaimType}
    for name in forbidden_names:
        assert name not in valid_names
    with pytest.raises(ValueError, match="BULLISH"):
        SemanticClaimType("BULLISH")


# --- 9/10/11/12: Claim Text Validation ------------------------------------------


def test_empty_claim_text_rejected() -> None:
    doc = _single_member_doc(_ix("jpcrp_cor:X", "内容"))
    member = doc.members[0]
    span = EvidenceSpan.from_text_block(document=doc, member=member, text_block=member.text_blocks[0])
    with pytest.raises(SemanticClaimSchemaError):
        _build_claim(span, text="")


def test_whitespace_only_claim_text_rejected() -> None:
    doc = _single_member_doc(_ix("jpcrp_cor:X", "内容"))
    member = doc.members[0]
    span = EvidenceSpan.from_text_block(document=doc, member=member, text_block=member.text_blocks[0])
    with pytest.raises(SemanticClaimSchemaError):
        _build_claim(span, text="   \n\t  ")


def test_control_character_claim_text_rejected() -> None:
    doc = _single_member_doc(_ix("jpcrp_cor:X", "内容"))
    member = doc.members[0]
    span = EvidenceSpan.from_text_block(document=doc, member=member, text_block=member.text_blocks[0])
    with pytest.raises(SemanticClaimSchemaError):
        _build_claim(span, text="内容\x00異常")


def test_claim_text_exactly_equal_to_supporting_quote_is_allowed() -> None:
    doc = _single_member_doc(_ix("jpcrp_cor:BusinessRisksTextBlock", "重要な変更はありません。"))
    member = doc.members[0]
    span = EvidenceSpan.from_text_block(document=doc, member=member, text_block=member.text_blocks[0])
    claim = _build_claim(span, text=span.supporting_quote)
    assert claim.normalized_claim_text == span.supporting_quote


# --- 13-20: semantic_identity_key / claim_id Identity Properties --------------


def test_same_semantic_input_produces_deterministic_semantic_identity_key() -> None:
    doc = _single_member_doc(_ix("jpcrp_cor:X", "内容"))
    member = doc.members[0]
    span = EvidenceSpan.from_text_block(document=doc, member=member, text_block=member.text_blocks[0])

    key_1 = compute_semantic_identity_key(
        document_id=span.document_id,
        source_raw_canonical_content_hash=span.source_raw_canonical_content_hash,
        source_normalizer_version=span.source_normalizer_version,
        member_path=span.member_path,
        taxonomy_element_name=span.taxonomy_element_name,
        occurrence_index=span.occurrence_index,
        char_start=span.char_start,
        char_end=span.char_end,
        claim_type=SemanticClaimType.BUSINESS_RISK,
        normalized_claim_text="claim text",
        schema_version="SCHEMA_V1",
    )
    key_2 = compute_semantic_identity_key(
        document_id=span.document_id,
        source_raw_canonical_content_hash=span.source_raw_canonical_content_hash,
        source_normalizer_version=span.source_normalizer_version,
        member_path=span.member_path,
        taxonomy_element_name=span.taxonomy_element_name,
        occurrence_index=span.occurrence_index,
        char_start=span.char_start,
        char_end=span.char_end,
        claim_type=SemanticClaimType.BUSINESS_RISK,
        normalized_claim_text="claim text",
        schema_version="SCHEMA_V1",
    )
    assert key_1 == key_2


def test_extraction_version_change_changes_claim_id_only() -> None:
    doc = _single_member_doc(_ix("jpcrp_cor:X", "内容"))
    member = doc.members[0]
    span = EvidenceSpan.from_text_block(document=doc, member=member, text_block=member.text_blocks[0])

    claim_v1 = _build_claim(span, extraction_version="EXTRACT_V1")
    claim_v2 = _build_claim(span, extraction_version="EXTRACT_V2")

    assert claim_v1.semantic_identity_key == claim_v2.semantic_identity_key
    assert claim_v1.claim_id != claim_v2.claim_id


def test_raw_hash_change_changes_semantic_identity() -> None:
    key_a = compute_semantic_identity_key(
        document_id="DOC1",
        source_raw_canonical_content_hash="hash-a",
        source_normalizer_version="NORM_V1",
        member_path="m.htm",
        taxonomy_element_name="jpcrp_cor:X",
        occurrence_index=0,
        char_start=0,
        char_end=4,
        claim_type=SemanticClaimType.BUSINESS_RISK,
        normalized_claim_text="text",
        schema_version="SCHEMA_V1",
    )
    key_b = compute_semantic_identity_key(
        document_id="DOC1",
        source_raw_canonical_content_hash="hash-b",
        source_normalizer_version="NORM_V1",
        member_path="m.htm",
        taxonomy_element_name="jpcrp_cor:X",
        occurrence_index=0,
        char_start=0,
        char_end=4,
        claim_type=SemanticClaimType.BUSINESS_RISK,
        normalized_claim_text="text",
        schema_version="SCHEMA_V1",
    )
    assert key_a != key_b


def test_normalizer_version_change_changes_semantic_identity() -> None:
    base = {
        "document_id": "DOC1",
        "source_raw_canonical_content_hash": "hash-a",
        "member_path": "m.htm",
        "taxonomy_element_name": "jpcrp_cor:X",
        "occurrence_index": 0,
        "char_start": 0,
        "char_end": 4,
        "claim_type": SemanticClaimType.BUSINESS_RISK,
        "normalized_claim_text": "text",
        "schema_version": "SCHEMA_V1",
    }
    key_a = compute_semantic_identity_key(source_normalizer_version="NORM_V1", **base)
    key_b = compute_semantic_identity_key(source_normalizer_version="NORM_V2", **base)
    assert key_a != key_b


def test_offset_change_changes_semantic_identity() -> None:
    base = {
        "document_id": "DOC1",
        "source_raw_canonical_content_hash": "hash-a",
        "source_normalizer_version": "NORM_V1",
        "member_path": "m.htm",
        "taxonomy_element_name": "jpcrp_cor:X",
        "occurrence_index": 0,
        "claim_type": SemanticClaimType.BUSINESS_RISK,
        "normalized_claim_text": "text",
        "schema_version": "SCHEMA_V1",
    }
    key_a = compute_semantic_identity_key(char_start=0, char_end=4, **base)
    key_b = compute_semantic_identity_key(char_start=1, char_end=5, **base)
    assert key_a != key_b


def test_claim_type_change_changes_semantic_identity() -> None:
    base = {
        "document_id": "DOC1",
        "source_raw_canonical_content_hash": "hash-a",
        "source_normalizer_version": "NORM_V1",
        "member_path": "m.htm",
        "taxonomy_element_name": "jpcrp_cor:X",
        "occurrence_index": 0,
        "char_start": 0,
        "char_end": 4,
        "normalized_claim_text": "text",
        "schema_version": "SCHEMA_V1",
    }
    key_a = compute_semantic_identity_key(claim_type=SemanticClaimType.BUSINESS_RISK, **base)
    key_b = compute_semantic_identity_key(claim_type=SemanticClaimType.OUTLOOK, **base)
    assert key_a != key_b


def test_claim_text_change_changes_semantic_identity() -> None:
    base = {
        "document_id": "DOC1",
        "source_raw_canonical_content_hash": "hash-a",
        "source_normalizer_version": "NORM_V1",
        "member_path": "m.htm",
        "taxonomy_element_name": "jpcrp_cor:X",
        "occurrence_index": 0,
        "char_start": 0,
        "char_end": 4,
        "claim_type": SemanticClaimType.BUSINESS_RISK,
        "schema_version": "SCHEMA_V1",
    }
    key_a = compute_semantic_identity_key(normalized_claim_text="text A", **base)
    key_b = compute_semantic_identity_key(normalized_claim_text="text B", **base)
    assert key_a != key_b


def test_schema_version_change_changes_semantic_identity() -> None:
    base = {
        "document_id": "DOC1",
        "source_raw_canonical_content_hash": "hash-a",
        "source_normalizer_version": "NORM_V1",
        "member_path": "m.htm",
        "taxonomy_element_name": "jpcrp_cor:X",
        "occurrence_index": 0,
        "char_start": 0,
        "char_end": 4,
        "claim_type": SemanticClaimType.BUSINESS_RISK,
        "normalized_claim_text": "text",
    }
    key_a = compute_semantic_identity_key(schema_version="SCHEMA_V1", **base)
    key_b = compute_semantic_identity_key(schema_version="SCHEMA_V2", **base)
    assert key_a != key_b


# --- 21: Creation/Order Independence --------------------------------------------


def test_creation_order_independence() -> None:
    doc = _single_member_doc(_ix("jpcrp_cor:X", "内容"))
    member = doc.members[0]
    span = EvidenceSpan.from_text_block(document=doc, member=member, text_block=member.text_blocks[0])

    # 無関係なClaimを先に作ってから対象Claimを作っても、対象ClaimのIDは
    # 作成順に依存しない(D0102.1要件I)。
    _unrelated_1 = _build_claim(span, claim_type=SemanticClaimType.OUTLOOK, text="unrelated 1")
    target_first = _build_claim(span, claim_type=SemanticClaimType.BUSINESS_RISK, text="target")
    _unrelated_2 = _build_claim(span, claim_type=SemanticClaimType.CAPITAL_ALLOCATION, text="unrelated 2")
    target_second = _build_claim(span, claim_type=SemanticClaimType.BUSINESS_RISK, text="target")

    assert target_first.claim_id == target_second.claim_id
    assert target_first.semantic_identity_key == target_second.semantic_identity_key


# --- 22: supersedes_claim_id defaults None --------------------------------------


def test_supersedes_claim_id_defaults_none() -> None:
    doc = _single_member_doc(_ix("jpcrp_cor:X", "内容"))
    member = doc.members[0]
    span = EvidenceSpan.from_text_block(document=doc, member=member, text_block=member.text_blocks[0])
    claim = _build_claim(span)
    assert claim.supersedes_claim_id is None


# --- 23-28: Revalidation ---------------------------------------------------------


def test_supporting_quote_tampering_fails_revalidation() -> None:
    doc = _single_member_doc(_ix("jpcrp_cor:X", "正しい内容"))
    member = doc.members[0]
    span = EvidenceSpan.from_text_block(document=doc, member=member, text_block=member.text_blocks[0])
    object.__setattr__(span, "supporting_quote", "改ざんされた内容XX")  # frozen dataclassをTest目的でBypass

    with pytest.raises(SemanticClaimSchemaError):
        revalidate_evidence_span(span, document=doc)


def test_out_of_bounds_span_fails_closed() -> None:
    doc = _single_member_doc(_ix("jpcrp_cor:X", "正しい内容"))
    member = doc.members[0]
    real_block = member.text_blocks[0]
    bogus_span = EvidenceSpan(
        document_id=doc.document_id,
        source_raw_canonical_content_hash=doc.raw_canonical_content_hash,
        source_normalizer_version=doc.normalizer_version,
        member_path=member.member_path,
        taxonomy_element_name=real_block.taxonomy_element_name,
        occurrence_index=real_block.occurrence_index,
        char_start=100_000,
        char_end=100_010,
        supporting_quote="X" * 10,
    )
    with pytest.raises(SemanticClaimSchemaError):
        revalidate_evidence_span(bogus_span, document=doc)


def test_normalizer_version_mismatch_needs_revalidation() -> None:
    doc = _single_member_doc(_ix("jpcrp_cor:X", "内容"))
    member = doc.members[0]
    span = EvidenceSpan.from_text_block(document=doc, member=member, text_block=member.text_blocks[0])
    object.__setattr__(span, "source_normalizer_version", "SOME_OTHER_NORMALIZER_VERSION")

    assert revalidate_evidence_span(span, document=doc) == RevalidationResult.NEEDS_REVALIDATION


def test_raw_hash_mismatch_needs_revalidation() -> None:
    doc = _single_member_doc(_ix("jpcrp_cor:X", "内容"))
    member = doc.members[0]
    span = EvidenceSpan.from_text_block(document=doc, member=member, text_block=member.text_blocks[0])
    object.__setattr__(span, "source_raw_canonical_content_hash", "0" * 64)

    assert revalidate_evidence_span(span, document=doc) == RevalidationResult.NEEDS_REVALIDATION


def test_wrong_member_or_text_block_identity_fails_closed() -> None:
    doc = _single_member_doc(_ix("jpcrp_cor:X", "内容"))
    member = doc.members[0]
    span = EvidenceSpan.from_text_block(document=doc, member=member, text_block=member.text_blocks[0])
    object.__setattr__(span, "taxonomy_element_name", "jpcrp_cor:DoesNotExist")

    with pytest.raises(SemanticClaimSchemaError):
        revalidate_evidence_span(span, document=doc)


def test_persisted_correct_span_revalidates_successfully() -> None:
    doc = _single_member_doc(_ix("jpcrp_cor:X", "内容"))
    member = doc.members[0]
    span = EvidenceSpan.from_text_block(document=doc, member=member, text_block=member.text_blocks[0])

    assert revalidate_evidence_span(span, document=doc) == RevalidationResult.VALID


# --- 29/30: Entity/Unicode保持 ---------------------------------------------------


def test_entity_looking_text_remains_unchanged_through_factory() -> None:
    doc = _single_member_doc(_ix("jpcrp_cor:X", "&amp;lt;タグ&amp;gt;"))
    member = doc.members[0]
    span = EvidenceSpan.from_text_block(document=doc, member=member, text_block=member.text_blocks[0])
    assert span.supporting_quote == "&lt;タグ&gt;"  # D0101.1のEntity単回Decode方針をそのまま反映


def test_japanese_punctuation_unicode_remains_unchanged_in_evidence() -> None:
    text = "１【事業等のリスク】重要な変更はありません。"
    doc = _single_member_doc(_ix("jpcrp_cor:X", text))
    member = doc.members[0]
    span = EvidenceSpan.from_text_block(document=doc, member=member, text_block=member.text_blocks[0])
    assert span.supporting_quote == text


# --- 31: Hidden Contentが再出現しないこと ----------------------------------------


def test_hidden_content_excluded_by_normalization_cannot_reappear_through_factory() -> None:
    visible = _ix("jpcrp_cor:BusinessRisksTextBlock", "可視Fact")
    hidden = f'<div style="display:none">{_ix("jpcrp_cor:HiddenFactTextBlock", "非表示Fact")}</div>'
    doc = _single_member_doc(visible + hidden)
    member = doc.members[0]

    assert len(member.text_blocks) == 1
    span = EvidenceSpan.from_text_block(document=doc, member=member, text_block=member.text_blocks[0])
    assert "非表示Fact" not in span.supporting_quote


# --- 32: REVIEW_REQUIREDが完全Accepted状態を偽装できないこと -------------------


def test_review_required_state_cannot_masquerade_as_fully_accepted() -> None:
    doc = _single_member_doc(_ix("jpcrp_cor:X", "内容"))
    member = doc.members[0]
    span = EvidenceSpan.from_text_block(document=doc, member=member, text_block=member.text_blocks[0])

    with pytest.raises(SemanticClaimSchemaError):
        _build_claim_with_explicit_review_flag(span, outcome=FaithfulnessOutcome.ACCEPT, review_required=True)
    with pytest.raises(SemanticClaimSchemaError):
        _build_claim_with_explicit_review_flag(span, outcome=FaithfulnessOutcome.REVIEW_REQUIRED, review_required=False)
    with pytest.raises(SemanticClaimSchemaError):
        _build_claim_with_explicit_review_flag(span, outcome=FaithfulnessOutcome.REJECT, review_required=False)

    ok = _build_claim_with_explicit_review_flag(span, outcome=FaithfulnessOutcome.REVIEW_REQUIRED, review_required=True)
    assert ok.faithfulness_review_required is True


def _build_claim_with_explicit_review_flag(
    span: EvidenceSpan, *, outcome: FaithfulnessOutcome, review_required: bool
) -> SemanticClaim:
    semantic_identity_key = compute_semantic_identity_key(
        document_id=span.document_id,
        source_raw_canonical_content_hash=span.source_raw_canonical_content_hash,
        source_normalizer_version=span.source_normalizer_version,
        member_path=span.member_path,
        taxonomy_element_name=span.taxonomy_element_name,
        occurrence_index=span.occurrence_index,
        char_start=span.char_start,
        char_end=span.char_end,
        claim_type=SemanticClaimType.BUSINESS_RISK,
        normalized_claim_text="text",
        schema_version="SCHEMA_V1",
    )
    claim_id = compute_claim_id(semantic_identity_key=semantic_identity_key, extraction_version="EXTRACT_V1")
    return SemanticClaim(
        claim_id=claim_id,
        semantic_identity_key=semantic_identity_key,
        claim_type=SemanticClaimType.BUSINESS_RISK,
        normalized_claim_text="text",
        direction=ClaimDirection.UNSPECIFIED,
        evidence_span=span,
        faithfulness_outcome=outcome,
        faithfulness_review_required=review_required,
        extraction_version="EXTRACT_V1",
        schema_version="SCHEMA_V1",
    )


# --- 33: generated_atがRevalidation/PIT判定に一切使われない ---------------------


def test_generated_at_never_consulted_by_revalidation() -> None:
    doc = _single_member_doc(_ix("jpcrp_cor:X", "内容"))
    member = doc.members[0]
    span = EvidenceSpan.from_text_block(document=doc, member=member, text_block=member.text_blocks[0])

    # extraction_provenance(generated_atを含む)を全く与えずに構築したClaim
    # でも、Revalidationは(evidence_span/documentのみを見て)正常に動作する
    # ——generated_atがどこにも参照されていないことの機能的な確認。
    claim = build_semantic_claim(
        claim_type=SemanticClaimType.BUSINESS_RISK,
        normalized_claim_text="text",
        direction=ClaimDirection.UNSPECIFIED,
        evidence_span=span,
        faithfulness_outcome=FaithfulnessOutcome.ACCEPT,
        extraction_version="EXTRACT_V1",
        extraction_provenance=None,
    )
    assert claim.extraction_provenance is None
    assert revalidate_evidence_span(claim.evidence_span, document=doc) == RevalidationResult.VALID


# --- 34: 完全に同一のConstructionは同一IDを得る(Idempotency) --------------------


def test_exact_duplicate_construction_yields_same_ids() -> None:
    doc = _single_member_doc(_ix("jpcrp_cor:X", "内容"))
    member = doc.members[0]
    span = EvidenceSpan.from_text_block(document=doc, member=member, text_block=member.text_blocks[0])

    claim_1 = _build_claim(span, text="同一のClaim")
    claim_2 = _build_claim(span, text="同一のClaim")

    assert claim_1.claim_id == claim_2.claim_id
    assert claim_1.semantic_identity_key == claim_2.semantic_identity_key


# --- 35: 異なるEvidence Provenance + 同一Claim Text -> 異なるsemantic_identity_key


def test_different_evidence_provenance_same_claim_text_yields_distinct_identity() -> None:
    body = _ix("jpcrp_cor:NoteA", "同一のClaim対象文言") + _ix("jpcrp_cor:NoteB", "同一のClaim対象文言")
    doc = _single_member_doc(body)
    member = doc.members[0]
    span_a = EvidenceSpan.from_text_block(document=doc, member=member, text_block=member.text_blocks[0])
    span_b = EvidenceSpan.from_text_block(document=doc, member=member, text_block=member.text_blocks[1])

    claim_a = _build_claim(span_a, text="同一のSemantic Claim Text")
    claim_b = _build_claim(span_b, text="同一のSemantic Claim Text")

    assert claim_a.normalized_claim_text == claim_b.normalized_claim_text
    assert claim_a.semantic_identity_key != claim_b.semantic_identity_key
    assert claim_a.claim_id != claim_b.claim_id
