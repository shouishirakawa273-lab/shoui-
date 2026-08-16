"""DisclosureDocumentからEvidenceを作る(Phase4B-1、D0045)。

**Core Principleの再確認**: 作れるのはDocument公開というFACTのみ
(例:「7203が2024-05-08にFY決算短信『...』を公開した」)。本文の内容
(会社予想・経営陣の見通し・計画等)はこのPhaseでは一切FACTへ変換しない
(本文Semantic Extractionは将来Phase)。`EvidenceRelation`(SUPPORTS/
CONTRADICTS等)はHypothesisが存在しない限り付与しない(既存`EvidenceRecord`
Schema自体にRelation Fieldが無い設計、D0040のまま踏襲)。
"""

from __future__ import annotations

from datetime import datetime

from lib.disclosures.model import DisclosureDocument
from lib.evidence.model import DataLayer, EvidenceRecord, EvidenceType
from lib.sources.catalog import DataCapability, PrimaryOrSecondary, SourceAuthorityClass, SourceMetadata


def disclosure_document_to_evidence(
    document: DisclosureDocument, *, source_authority_class: SourceAuthorityClass
) -> EvidenceRecord:
    """開示されたという事実のみをFACTとして記述する(本文の解釈を加えない)。

    `source_authority_class`はSource非依存のこのModuleでは推測できないため、
    呼び出し側に必須Keyword引数として要求する(TDnet/EDINET等の制度的開示は
    `PRIMARY_OFFICIAL`、企業IRは`COMPANY_PRIMARY`が想定されるが、実Source未接続の
    Phase4B-1ではこのModule自身が決め打ちしない、D0045)。

    `source.available_at`には`document.market_public_at`(無ければ
    `document.retrieved_at`)を使う。これはFundamentals Phase4Aの
    `disclosure_metric_to_evidence()`と同じ保守的な選択である
    (`market_public_at`は`provider_available_at`以前であるため、
    `available_at`を過大評価しない)。
    """
    entity_label = document.entity_id or document.internal_document_id
    content = (
        f"{entity_label}: 「{document.title}」({document.document_kind.value})を公開"
        f"(source_document_id={document.source_document_id})"
    )
    available_at: datetime = document.market_public_at or document.retrieved_at
    source = SourceMetadata(
        source_id=document.internal_document_id,
        source_type="DISCLOSURE_DOCUMENT",
        provider_name=document.delivery_provider or document.originating_source or "UNKNOWN",
        source_authority_class=source_authority_class,
        primary_or_secondary=PrimaryOrSecondary.PRIMARY,
        retrieved_at=document.retrieved_at,
        published_at=document.market_public_at,
        available_at=available_at,
        originating_source=document.originating_source,
        delivery_provider=document.delivery_provider,
        provenance_id=document.provenance_id,
    )
    related_codes = () if document.entity_id is None else (document.entity_id,)
    return EvidenceRecord(
        evidence_id=f"EVID_DOC_{document.internal_document_id}",
        evidence_type=EvidenceType.FACT,
        layer=DataLayer.NORMALIZED,
        capability=DataCapability.DISCLOSURE,
        content=content,
        source=source,
        related_codes=related_codes,
        provenance_id=document.provenance_id,
    )


__all__ = ["disclosure_document_to_evidence"]
