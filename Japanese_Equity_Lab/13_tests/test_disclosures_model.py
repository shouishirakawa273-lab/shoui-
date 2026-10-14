"""Phase4B-1(D0045): Disclosure Common Core Schema(`DisclosureDocument`/
`DisclosureAttachment`/`DocumentRelationship`)のテスト。
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from lib.disclosures.model import (
    DisclosureAttachment,
    DisclosureDocument,
    DocumentKind,
    DocumentRelationship,
    DocumentRelationshipKind,
)


def _document(**overrides: object) -> DisclosureDocument:
    defaults: dict[str, object] = dict(
        internal_document_id="DOC_1",
        title="テスト開示",
        retrieved_at=datetime(2024, 1, 1, tzinfo=UTC),
    )
    defaults.update(overrides)
    return DisclosureDocument(**defaults)  # type: ignore[arg-type]


def test_disclosure_document_requires_tz_aware_retrieved_at() -> None:
    with pytest.raises(ValueError, match="tz-aware"):
        DisclosureDocument(internal_document_id="DOC_1", title="x", retrieved_at=datetime(2024, 1, 1))


def test_disclosure_document_requires_tz_aware_market_public_at() -> None:
    with pytest.raises(ValueError, match="tz-aware"):
        _document(market_public_at=datetime(2024, 1, 1))


def test_disclosure_document_requires_tz_aware_provider_available_at() -> None:
    with pytest.raises(ValueError, match="tz-aware"):
        _document(provider_available_at=datetime(2024, 1, 1))


def test_disclosure_document_defaults_are_conservative() -> None:
    document = _document()
    assert document.market_public_at is None
    assert document.provider_available_at is None
    assert document.document_kind == DocumentKind.UNKNOWN
    assert document.entity_id is None
    assert document.source_document_id is None
    assert document.language is None
    assert document.attachments == ()


def test_disclosure_attachment_requires_tz_aware_retrieved_at() -> None:
    with pytest.raises(ValueError, match="tz-aware"):
        DisclosureAttachment(
            attachment_id="A1",
            document_internal_id="DOC_1",
            retrieved_at=datetime(2024, 1, 1),
        )


def test_document_kind_covers_minimum_common_taxonomy() -> None:
    expected = {
        DocumentKind.FINANCIAL_RESULTS,
        DocumentKind.FORECAST,
        DocumentKind.DIVIDEND,
        DocumentKind.CAPITAL_POLICY,
        DocumentKind.SHARE_REPURCHASE,
        DocumentKind.M_AND_A,
        DocumentKind.GOVERNANCE,
        DocumentKind.SECURITIES_REPORT,
        DocumentKind.LARGE_SHAREHOLDING,
        DocumentKind.MATERIAL_EVENT,
        DocumentKind.OTHER,
        DocumentKind.UNKNOWN,
    }
    assert expected == set(DocumentKind)


# --- Test 13: unknown relationship remains unknown(自動で他の種別へ昇格しない) ---


def test_document_relationship_unknown_kind_is_preserved_not_upgraded() -> None:
    relationship = DocumentRelationship(
        relationship_id="REL_1",
        from_document_id="DOC_1",
        to_document_id="DOC_2",
        basis="関係の存在自体はProvider Metadataで確認できたが、種別までは確認できなかった",
    )
    assert relationship.relationship_kind == DocumentRelationshipKind.UNKNOWN
    assert relationship.relationship_kind != DocumentRelationshipKind.CORRECTS
    assert relationship.relationship_kind != DocumentRelationshipKind.RESTATES
