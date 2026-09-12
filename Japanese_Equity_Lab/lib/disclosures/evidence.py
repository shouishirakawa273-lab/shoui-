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
from lib.evidence.model import AvailabilityBasis, DataLayer, EvidenceRecord, EvidenceType
from lib.sources.catalog import DataCapability, PrimaryOrSecondary, SourceAuthorityClass, SourceMetadata


def disclosure_document_to_evidence(
    document: DisclosureDocument, *, source_authority_class: SourceAuthorityClass
) -> EvidenceRecord:
    """開示されたという事実のみをFACTとして記述する(本文の解釈を加えない)。

    `source_authority_class`はSource非依存のこのModuleでは推測できないため、
    呼び出し側に必須Keyword引数として要求する(TDnet/EDINET等の制度的開示は
    `PRIMARY_OFFICIAL`、企業IRは`COMPANY_PRIMARY`が想定されるが、実Source未接続の
    Phase4B-1ではこのModule自身が決め打ちしない、D0045)。

    **PIT Bugfix(D0050で修正、旧実装の問題点)**: 旧実装は`source.
    available_at = document.market_public_at or document.retrieved_at`と
    していた。これは`lib.fundamentals.evidence.disclosure_metric_to_
    evidence()`が持っていたのと同型のBug(D0049で修正済み)であり、
    Common Core側では未修正のまま残っていた。`market_public_at`(市場
    公表時刻、A系統)は通常`provider_available_at`(Provider経由で実際に
    参照可能になった時刻、B系統)より**早い**。この早い時刻を
    `EvidenceRecord.is_usable_at()`が直接参照する`available_at`
    (`self.source.available_at <= decision_at`)へ代入すると、実際には
    まだ研究所側で取得可能でなかった時点を「利用可能だった」と誤認する
    (Future Leakage)。旧Docstringの「market_public_atは保守的だから
    available_atを過大評価しない」という説明は論理が逆だった(D0049の
    Fundamentals側修正と同じ誤り)。

    `DisclosureDocument`は`market_public_at`/`market_public_at_basis`
    とは別に`provider_available_at`/`provider_available_at_basis`を
    Field として持つ(Fundamentalsの`DisclosureEnvelope`には無い
    Field、`lib.disclosures.model.DisclosureDocument`Docstring参照)。
    したがって`source.available_at`は次の優先順位で決定する: (1)
    `provider_available_at`が確認済み(`provider_available_at_basis
    != AvailabilityBasis.UNKNOWN`)であればそれを使う、(2)確認できな
    ければ`document.retrieved_at`(Observed Factとしての下限)を使う。
    **`market_public_at`へは決してFallbackしない**。現在(D0050時点)
    EDINET/TDnetいずれのNormalizerも`provider_available_at`を確認済み
    値として設定しないため(常に`UNKNOWN`Basis)、実際には常に(2)の
    経路が使われるが、将来Providerが`provider_available_at`を確認済み
    で提供するようになった場合にも、このFieldを自動的に活用できる設計
    にしている(`market_public_at`FallbackをやめるMinimal Changeであり、
    新規Schema Field追加は行っていない)。

    **重要な注意(pit-auditor Finding、D0045追記。D0050で解消済み)**:
    `SourceMetadata`には`availability_basis`相当のFieldが無いため、
    上記の優先順位判定はこの関数内で行い、結果のみを`SourceMetadata.
    available_at`へ渡す。これにより、この関数の戻り値をそのまま
    `lib.evidence.retrieval`の汎用PIT Filter(`filter_usable_at()`)へ
    渡しても、`market_public_at`起因のFuture Leakageは発生しない
    (`disclosures_as_of()`による事前Filterへの依存が無くなった)。
    """
    if document.provider_available_at is not None and document.provider_available_at_basis != AvailabilityBasis.UNKNOWN:
        available_at: datetime = document.provider_available_at
    else:
        available_at = document.retrieved_at
    entity_label = document.entity_id or document.internal_document_id
    content = (
        f"{entity_label}: 「{document.title}」({document.document_kind.value})を公開"
        f"(source_document_id={document.source_document_id})"
    )
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
