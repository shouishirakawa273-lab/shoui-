"""`company_ir_normalize.build_company_ir_document()`のTest(Phase4B-4)。
Test IDはユーザーTask仕様のIR-007〜011/014に対応する(期待値はSource
Integration Skill v1のPIT-*/EVIDENCE-*/RAW-*Ruleから導出する)。
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from lib.disclosures.evidence import disclosure_document_to_evidence
from lib.disclosures.model import DocumentKind
from lib.disclosures.providers.company_ir import ComplianceError
from lib.disclosures.providers.company_ir_normalize import build_company_ir_document
from lib.evidence.model import AvailabilityBasis
from lib.sources.catalog import SourceAuthorityClass

RETRIEVED_AT = datetime(2026, 8, 18, 12, 0, tzinfo=UTC)


def _base_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "requested_url": "https://ir.example.co.jp/news/x.html",
        "final_url": "https://ir.example.co.jp/news/x.html",
        "requested_domain": "ir.example.co.jp",
        "final_domain": "ir.example.co.jp",
        "redirect_chain": [],
        "http_status": 200,
        "headers": {"Content-Type": "text/html", "Last-Modified": "Tue, 18 Aug 2026 03:00:00 GMT"},
        "content_length_observed": 1234,
        "compliance": {
            "terms_checked": True,
            "robots_checked": True,
            "automated_retrieval": "ALLOWED",
            "redistribution": "UNCLEAR",
            "retention": "UNCLEAR",
            "attribution_required": "NOT_CHECKED",
            "checked_by": "USER_MANUAL_REVIEW_2026-08-18",
            "checked_at": "2026-08-18T09:00:00+00:00",
            "notes": "",
        },
    }
    payload.update(overrides)
    return payload


# --- IR-007: No Market Public Guess ---


def test_ir007_no_market_public_at_when_not_supplied() -> None:
    document, _meta = build_company_ir_document(
        _base_payload(), internal_document_id="DOC_1", title="決算に関するお知らせ", retrieved_at=RETRIEVED_AT
    )
    assert document.market_public_at is None
    assert document.market_public_at_basis == AvailabilityBasis.UNKNOWN


def test_ir007_basis_forced_unknown_when_value_absent() -> None:
    """`market_public_at`を渡さずに`market_public_at_basis`だけEXACTを
    渡そうとすると、値の無い確信度という矛盾状態をFail Closedで拒否する。"""
    with pytest.raises(ValueError, match="market_public_at"):
        build_company_ir_document(
            _base_payload(),
            internal_document_id="DOC_1",
            title="決算に関するお知らせ",
            retrieved_at=RETRIEVED_AT,
            market_public_at=None,
            market_public_at_basis=AvailabilityBasis.EXACT,
        )


def test_ir007_explicit_confirmed_timestamp_is_accepted() -> None:
    """呼び出し側が明示的に確認済みTimestampを渡した場合のみ設定される
    (HTML本文からの自動抽出ではない、という設計そのものをこのTestが
    示す — Adapter/Normalizerのどこにも日付文字列Parse Codeが無い)。"""
    confirmed = datetime(2026, 8, 18, 15, 0, tzinfo=UTC)
    document, _meta = build_company_ir_document(
        _base_payload(),
        internal_document_id="DOC_1",
        title="決算に関するお知らせ",
        retrieved_at=RETRIEVED_AT,
        market_public_at=confirmed,
        market_public_at_basis=AvailabilityBasis.EXACT,
    )
    assert document.market_public_at == confirmed
    assert document.market_public_at_basis == AvailabilityBasis.EXACT


# --- IR-008: HTTP Last-Modified Is Not Provider Availability ---


def test_ir008_last_modified_never_mapped_to_provider_available_at() -> None:
    document, metadata = build_company_ir_document(
        _base_payload(), internal_document_id="DOC_1", title="お知らせ", retrieved_at=RETRIEVED_AT
    )
    assert document.provider_available_at is None
    assert document.provider_available_at_basis == AvailabilityBasis.UNKNOWN
    # Last-ModifiedはOpaqueなstrとしてのみMetadataへ保持される(datetimeへ変換されない)。
    assert metadata.http_last_modified_raw == "Tue, 18 Aug 2026 03:00:00 GMT"
    assert isinstance(metadata.http_last_modified_raw, str)


def test_ir008_no_provider_available_at_parameter_exists_in_signature() -> None:
    """`build_company_ir_document()`のSignature自体に`provider_available_at`
    引数が存在しないこと(構造的に設定不可能であることの直接確認、
    誤用の余地が無い設計)。"""
    import inspect

    sig = inspect.signature(build_company_ir_document)
    assert "provider_available_at" not in sig.parameters


# --- IR-009: Retrieved At PIT ---


def test_ir009_retrieved_at_used_as_pit_basis() -> None:
    document, _meta = build_company_ir_document(
        _base_payload(), internal_document_id="DOC_1", title="お知らせ", retrieved_at=RETRIEVED_AT
    )
    assert document.retrieved_at == RETRIEVED_AT

    evidence = disclosure_document_to_evidence(document, source_authority_class=SourceAuthorityClass.COMPANY_PRIMARY)
    # market_public_at/provider_available_atいずれも未確認のため、available_atはretrieved_atになる
    # (D0049/D0050で確立したCommon Core原則、Company IRでも同一のEvidence変換関数を再利用)。
    assert evidence.source.available_at == RETRIEVED_AT


# --- IR-010: Document Is Not Event ---


def test_ir010_document_kind_always_unknown_no_classification() -> None:
    document, _meta = build_company_ir_document(
        _base_payload(), internal_document_id="DOC_1", title="上方修正のお知らせ", retrieved_at=RETRIEVED_AT
    )
    assert document.document_kind == DocumentKind.UNKNOWN


def test_ir010_evidence_content_has_no_interpretive_language() -> None:
    document, _meta = build_company_ir_document(
        _base_payload(), internal_document_id="DOC_1", title="業績予想の上方修正に関するお知らせ", retrieved_at=RETRIEVED_AT
    )
    evidence = disclosure_document_to_evidence(document, source_authority_class=SourceAuthorityClass.COMPANY_PRIMARY)
    forbidden_terms = ("bullish", "bearish", "buy", "sell", "好調", "割安", "強気", "上昇要因", "好材料")
    for term in forbidden_terms:
        assert term not in evidence.content, f"Evidence Contentに解釈語 '{term}' が含まれています"


# --- IR-011: Duplicate Safety(構造確認、実装からDocumentRelationship/DuplicateRelationKindを参照しない) ---


def test_ir011_normalize_module_never_imports_relationship_or_duplicate_kind() -> None:
    import lib.disclosures.providers.company_ir_normalize as module

    source = module.__file__
    assert source is not None
    text = open(source, encoding="utf-8").read()
    assert "DocumentRelationship" not in text
    assert "DuplicateRelationKind" not in text


# --- IR-012: Timezone(Document側) ---


def test_ir012_market_public_at_requires_tz_aware() -> None:
    with pytest.raises(ValueError, match="tz-aware"):
        build_company_ir_document(
            _base_payload(),
            internal_document_id="DOC_1",
            title="お知らせ",
            retrieved_at=RETRIEVED_AT,
            market_public_at=datetime(2026, 8, 18, 15, 0),  # naive
            market_public_at_basis=AvailabilityBasis.EXACT,
        )


def test_ir012_retrieved_at_requires_tz_aware() -> None:
    with pytest.raises(ValueError, match="tz-aware"):
        build_company_ir_document(
            _base_payload(),
            internal_document_id="DOC_1",
            title="お知らせ",
            retrieved_at=datetime(2026, 8, 18, 12, 0),  # naive
        )


# --- Defense in depth: pit-auditor Finding(Phase4B-4) ---


def test_normalize_reasserts_compliance_and_fails_closed_on_hand_crafted_payload() -> None:
    """`CompanyIrAdapter.fetch_document_raw()`を経由しない、手組みの
    fetch_payload dict(automated_retrieval != ALLOWED)を渡した場合でも、
    `build_company_ir_document()`自身がFail Closedすることを確認する
    (pit-auditorが指摘した、Normalizer側にCompliance再確認が無かった
    Gapへの修正)。"""
    payload = _base_payload()
    payload["compliance"] = dict(payload["compliance"]) | {"automated_retrieval": "DISALLOWED"}
    with pytest.raises(ComplianceError):
        build_company_ir_document(payload, internal_document_id="DOC_1", title="お知らせ", retrieved_at=RETRIEVED_AT)


# --- IR-014: Common Core Regression(新規Evidence変換関数を作らず既存を再利用) ---


def test_ir014_reuses_existing_disclosure_document_to_evidence_without_new_function() -> None:
    """Company IR専用のEvidence変換関数を新設していないことの直接確認
    (Common CoreがProvider非依存であるという設計そのものの検証、
    Section 21)。"""
    document, _meta = build_company_ir_document(
        _base_payload(), internal_document_id="DOC_1", title="お知らせ", retrieved_at=RETRIEVED_AT
    )
    evidence = disclosure_document_to_evidence(document, source_authority_class=SourceAuthorityClass.COMPANY_PRIMARY)
    assert evidence.source.originating_source == "COMPANY_IR"
    assert evidence.source.delivery_provider == "COMPANY_IR"


def test_ir014_entity_id_not_guessed_stays_none_by_default() -> None:
    document, _meta = build_company_ir_document(
        _base_payload(), internal_document_id="DOC_1", title="お知らせ", retrieved_at=RETRIEVED_AT
    )
    assert document.entity_id is None


def test_ir014_entity_id_only_set_when_explicitly_supplied() -> None:
    document, _meta = build_company_ir_document(
        _base_payload(),
        internal_document_id="DOC_1",
        title="お知らせ",
        retrieved_at=RETRIEVED_AT,
        entity_id="7203",
    )
    assert document.entity_id == "7203"
