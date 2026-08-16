"""Phase4B-1(D0045): Disclosure Common Core Normalizerのテスト。

`13_tests/fixtures/disclosure_common_core_v1.json`はProvider-neutralな
合成Fixtureであり、実TDnet/EDINET/Company IRの生Wire Formatを模したもの
ではない(DECISIONS.md D0045参照)。
"""

from __future__ import annotations

import copy
import json
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from lib.disclosures.model import AttachmentKind, DocumentKind
from lib.disclosures.normalize import (
    find_exact_content_duplicate_groups,
    find_same_source_document_id_signals,
    parse_disclosure_payload,
)
from lib.sources.entity_registry import EntityIdentifierMapping, EntityRegistry, MappingConfidence

_FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "disclosure_common_core_v1.json"
_RETRIEVED_AT = datetime(2026, 1, 1, tzinfo=UTC)


def _load_payload() -> list[dict[str, object]]:
    return json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))["data"]


# --- Test 8: Raw payload immutable ---


def test_parsing_does_not_mutate_raw_payload() -> None:
    payload = _load_payload()
    payload_copy = copy.deepcopy(payload)
    parse_disclosure_payload(payload, retrieved_at=_RETRIEVED_AT)
    assert payload == payload_copy


# --- Test 11: 未知のDocumentKindはfail closed(即例外で全処理停止しない) ---


def test_unknown_document_kind_fails_closed_to_unknown_not_exception(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level("WARNING"):
        documents = parse_disclosure_payload(_load_payload(), retrieved_at=_RETRIEVED_AT)
    doc = next(d for d in documents if d.source_document_id == "FIX-D-004")
    assert doc.document_kind == DocumentKind.UNKNOWN
    assert "FIXTURE_UNKNOWN_KIND_NOT_IN_MAPPING_TABLE" in caplog.text


# --- Test 12: DocType文字列のsubstring推測をしない(部分一致では解決しない) ---


def test_doc_kind_mapping_does_not_use_substring_matching() -> None:
    """ "FIXTURE_DIVIDEND"は既知だが、それを含むだけの未知文字列は解決されない
    (Substring Heuristic禁止の構造的確認)。"""
    payload = [
        {
            "DocId": "SUBSTRING-TEST",
            "Code": "72030",
            "Title": "x",
            "DocKind": "FIXTURE_DIVIDEND_SPECIAL_CASE_NOT_REGISTERED",
            "PublicDate": "2024-01-01",
            "PublicTime": "10:00",
        }
    ]
    documents = parse_disclosure_payload(payload, retrieved_at=_RETRIEVED_AT)
    assert documents[0].document_kind == DocumentKind.UNKNOWN


# --- Test 5: unknown timestamp(PublicTime空文字列)はmarket_public_atをNoneにfail closed ---


def test_missing_public_time_yields_none_market_public_at_not_guessed() -> None:
    documents = parse_disclosure_payload(_load_payload(), retrieved_at=_RETRIEVED_AT)
    doc = next(d for d in documents if d.source_document_id == "FIX-D-005")
    assert doc.market_public_at is None
    from lib.evidence.model import AvailabilityBasis

    assert doc.market_public_at_basis == AvailabilityBasis.UNKNOWN


def test_market_public_at_is_tz_aware_asia_tokyo_when_both_fields_present() -> None:
    documents = parse_disclosure_payload(_load_payload(), retrieved_at=_RETRIEVED_AT)
    doc = next(d for d in documents if d.source_document_id == "FIX-D-001")
    assert doc.market_public_at == datetime(2024, 5, 8, 14, 0, tzinfo=ZoneInfo("Asia/Tokyo"))


# --- Test 6: provider_available_atは常にUNKNOWN Basis(実観測ログが無いため) ---


def test_provider_available_at_basis_is_always_unknown_no_real_observation_log() -> None:
    from lib.evidence.model import AvailabilityBasis

    documents = parse_disclosure_payload(_load_payload(), retrieved_at=_RETRIEVED_AT)
    doc = next(d for d in documents if d.source_document_id == "FIX-D-001")
    assert doc.provider_available_at is not None  # 構造上必須Fieldへの保守的Anchor
    assert doc.provider_available_at_basis == AvailabilityBasis.UNKNOWN


# --- Test 19/20: Attachment metadata保持・未知AttachmentKindのfail closed ---


def test_attachment_metadata_is_preserved() -> None:
    documents = parse_disclosure_payload(_load_payload(), retrieved_at=_RETRIEVED_AT)
    doc = next(d for d in documents if d.source_document_id == "FIX-D-001")
    assert len(doc.attachments) == 2
    kinds = {a.attachment_kind for a in doc.attachments}
    assert kinds == {AttachmentKind.PDF, AttachmentKind.XBRL}
    primary = [a for a in doc.attachments if a.is_primary]
    assert len(primary) == 1
    assert primary[0].filename == "fy_results.pdf"


def test_unknown_attachment_kind_fails_closed(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level("WARNING"):
        documents = parse_disclosure_payload(_load_payload(), retrieved_at=_RETRIEVED_AT)
    doc = next(d for d in documents if d.source_document_id == "FIX-D-004")
    assert len(doc.attachments) == 1
    assert doc.attachments[0].attachment_kind == AttachmentKind.UNKNOWN


# --- Test 9: Provider Schema Evolution、未知Rawフィールドでも壊れない ---


def test_unknown_extra_raw_field_does_not_break_normalizer() -> None:
    documents = parse_disclosure_payload(_load_payload(), retrieved_at=_RETRIEVED_AT)
    doc = next(d for d in documents if d.source_document_id == "FIX-D-008")
    assert doc.document_kind == DocumentKind.LARGE_SHAREHOLDING


def test_unknown_extra_raw_field_preserved_in_raw_payload() -> None:
    payload = _load_payload()
    row = next(r for r in payload if r.get("DocId") == "FIX-D-008")
    assert row["FutureProviderFieldNotYetKnown"] == "unrecognized-but-preserved"


# --- Test 21: Entity ResolutionはPIT-aware ---


def test_entity_registry_resolves_canonical_entity_id_when_mapped() -> None:
    registry = EntityRegistry(
        [
            EntityIdentifierMapping(
                issuer_id="ISSUER_TOYOTA",
                provider_identifiers={"disclosure_fixture": "72030"},
                canonical_name="トヨタ自動車",
                mapping_confidence=MappingConfidence.HIGH,
            )
        ]
    )
    documents = parse_disclosure_payload(_load_payload(), retrieved_at=_RETRIEVED_AT, entity_registry=registry)
    doc = next(d for d in documents if d.source_document_id == "FIX-D-001")
    assert doc.entity_id == "ISSUER_TOYOTA"


def test_entity_registry_leaves_entity_id_none_when_unmapped() -> None:
    registry = EntityRegistry([])
    documents = parse_disclosure_payload(_load_payload(), retrieved_at=_RETRIEVED_AT, entity_registry=registry)
    doc = next(d for d in documents if d.source_document_id == "FIX-D-001")
    assert doc.entity_id is None


def test_entity_registry_mapping_respects_pit_valid_from() -> None:
    """Mapping有効期間外(valid_from後)のas_ofでは解決しない(社名変更等の前に
    現在のissuer_idへ誤Mappingしない、PIT-aware原則)。"""
    registry = EntityRegistry(
        [
            EntityIdentifierMapping(
                issuer_id="ISSUER_TOYOTA_NEW",
                provider_identifiers={"disclosure_fixture": "72030"},
                canonical_name="トヨタ自動車(新)",
                valid_from=date_after_fixture(),
            )
        ]
    )
    documents = parse_disclosure_payload(_load_payload(), retrieved_at=_RETRIEVED_AT, entity_registry=registry)
    doc = next(d for d in documents if d.source_document_id == "FIX-D-001")
    assert doc.entity_id is None  # FIX-D-001のPublicDate(2024-05-08)はvalid_from以前


def date_after_fixture() -> object:
    from datetime import date

    return date(2025, 1, 1)


# --- Test 22: Origin Source != Delivery Provider ---


def test_originating_source_and_delivery_provider_are_kept_distinct() -> None:
    documents = parse_disclosure_payload(
        _load_payload(),
        retrieved_at=_RETRIEVED_AT,
        originating_source="TDNET_FIXTURE",
        delivery_provider="AGGREGATOR_FIXTURE",
    )
    doc = documents[0]
    assert doc.originating_source == "TDNET_FIXTURE"
    assert doc.delivery_provider == "AGGREGATOR_FIXTURE"
    assert doc.originating_source != doc.delivery_provider


# --- Test 16/17/18: Deduplication ---


def test_exact_content_duplicate_groups_detected_via_content_hash() -> None:
    payload = _load_payload()
    groups = find_exact_content_duplicate_groups(payload)
    duplicate_doc_ids = {payload[i]["DocId"] for indices in groups.values() for i in indices}
    assert "FIX-D-007" in duplicate_doc_ids
    # 完全一致した行のみがグループ化される(1件だけのHashはグループに含まれない)。
    for indices in groups.values():
        assert len(indices) >= 2


def test_same_source_document_id_signal_detected() -> None:
    documents = parse_disclosure_payload(_load_payload(), retrieved_at=_RETRIEVED_AT)
    signals = find_same_source_document_id_signals(documents)
    matching = [s for s in signals if "source_document_id=FIX-D-006" in s.basis]
    assert len(matching) == 1


def test_same_title_alone_does_not_trigger_duplicate_signal() -> None:
    """タイトルが同じでも、SourceIDが異なる/存在しなければDuplicate扱いしない
    (`find_same_source_document_id_signals`はTitleを一切参照しない構造上の
    保証)。"""
    payload = [
        {
            "DocId": "T1",
            "Code": "72030",
            "Title": "同一タイトル",
            "DocKind": "FIXTURE_OTHER",
            "PublicDate": "2024-01-01",
            "PublicTime": "10:00",
        },
        {
            "DocId": "T2",
            "Code": "67580",
            "Title": "同一タイトル",
            "DocKind": "FIXTURE_OTHER",
            "PublicDate": "2024-01-01",
            "PublicTime": "10:00",
        },
    ]
    documents = parse_disclosure_payload(payload, retrieved_at=_RETRIEVED_AT)
    signals = find_same_source_document_id_signals(documents)
    assert signals == []


def test_same_date_alone_does_not_trigger_duplicate_signal() -> None:
    """同じ会社・同じ日付というだけでは重複扱いしない(FIX-D-001/002は同一
    会社・同一日付だが別Content・別SourceIDのため、Signalが出ない)。"""
    documents = parse_disclosure_payload(_load_payload(), retrieved_at=_RETRIEVED_AT)
    signals = find_same_source_document_id_signals(documents)
    ids_involved = {s.document_a_id for s in signals} | {s.document_b_id for s in signals}
    toyota_docs = [d for d in documents if d.source_document_id in ("FIX-D-001", "FIX-D-002")]
    assert not any(d.internal_document_id in ids_involved for d in toyota_docs)


# --- Test 14/15: Relationshipを自動推測しない(構造的確認) ---


def test_parse_disclosure_payload_never_creates_relationship_records() -> None:
    """`parse_disclosure_payload`はDocumentRelationshipを一切生成しない
    (戻り値の型自体がlist[DisclosureDocument]のみであり、「後から出た文書だから
    前を訂正した」という時系列だけからの推測を構造的に不可能にしている)。"""
    import inspect

    from lib.disclosures import normalize as normalize_module

    signature = inspect.signature(normalize_module.parse_disclosure_payload)
    assert "DocumentRelationship" not in str(signature.return_annotation)


def test_module_never_references_corrects_or_restates_kind_automatically() -> None:
    """normalize.py自体がDocumentRelationshipKind.CORRECTS/RESTATESへ言及しない
    ことを確認する(自動Correction判定ロジックが存在しないことの構造的確認、
    Fundamentals Phase4Aのis_correction=False固定と同じ原則)。"""
    source = Path(__import__("lib.disclosures.normalize", fromlist=["__file__"]).__file__).read_text(encoding="utf-8")
    assert "CORRECTS" not in source
    assert "RESTATES" not in source
