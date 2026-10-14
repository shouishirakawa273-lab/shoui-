"""Disclosure Common Core Schema(Phase4B-1、D0045): Source非依存の開示文書Model。

**Core Principle**: Documentの「公開されたという事実」と、Document本文の
「内容の意味」を分離する。「2026-xx-xxにこの会社がこのTitleの文書を公開した」
はFACTとして扱えるが、本文に書かれた内容(会社予想・経営陣の見通し・計画等)を
自動的にFACT扱いしない。本文Semantic Extraction(数値抽出・Event分類・
Claim抽出)はPhase4B-1のScope外(将来Phase)。

## TDnet/EDINET/Company IRを将来同じArchitectureで扱うための設計

このPhaseでは実Sourceへ接続しない。以下のModelはProvider非依存であり、
特定のReal Providerの生Field名を前提としない(`normalize.py`のFixture用
Mapping Tableも同様にProvider-neutralである)。

## Actual Observed vs Confirmed Relationship

`DocumentRelationship`(Correction/Restatement/Replacement等)は、Providerが
明示するか、公式Metadataで確認できる場合のみ設定する。「後から出た文書だから
前を訂正した」という時系列だけからの推測は禁止する(Phase4Aの`is_correction`
原則と同じ、D0043参照)。Relationship不明の場合は`DocumentRelationship`
Record自体を作らない(存在するとは主張しない)か、種別のみ`UNKNOWN`とする。

## Append-only

過去のDisclosureDocumentを新しいDocumentで上書きしない。Correction/
Restatementであっても、古いDocumentは古いDocumentのまま保持し、明示的な
`DocumentRelationship`で結びつける(Phase4Aの`RevisionHistory`が過去
Versionを削除しないのと同じ原則)。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from lib.evidence.model import AvailabilityBasis

NORMALIZER_VERSION = "DISCLOSURE_COMMON_CORE_NORMALIZER_V1"


class DocumentKind(StrEnum):
    """Source非依存の最小Common Taxonomy。TDnet/EDINET固有の巨大Taxonomyを
    最初から作らない。Provider固有Codeからのmappingは`normalize.py`の
    明示的Mapping Tableのみで行い、substring heuristicは使わない。未知の
    Provider Codeは`UNKNOWN`へfail closedする。"""

    FINANCIAL_RESULTS = "FINANCIAL_RESULTS"
    FORECAST = "FORECAST"
    DIVIDEND = "DIVIDEND"
    CAPITAL_POLICY = "CAPITAL_POLICY"
    SHARE_REPURCHASE = "SHARE_REPURCHASE"
    M_AND_A = "M_AND_A"
    GOVERNANCE = "GOVERNANCE"
    SECURITIES_REPORT = "SECURITIES_REPORT"
    LARGE_SHAREHOLDING = "LARGE_SHAREHOLDING"
    MATERIAL_EVENT = "MATERIAL_EVENT"
    OTHER = "OTHER"
    UNKNOWN = "UNKNOWN"


class AttachmentKind(StrEnum):
    PDF = "PDF"
    XBRL = "XBRL"
    HTML = "HTML"
    CSV = "CSV"
    XML = "XML"
    OTHER = "OTHER"
    UNKNOWN = "UNKNOWN"


class AttachmentAvailability(StrEnum):
    """Attachmentの実体(bytes)をこのLabが保持しているかどうか。Phase4B-1は
    実Downloadを行わないため、既定は`METADATA_ONLY`(存在は分かるが内容は
    未取得)。"""

    METADATA_ONLY = "METADATA_ONLY"
    NOT_AVAILABLE = "NOT_AVAILABLE"
    UNKNOWN = "UNKNOWN"


class DocumentRelationshipKind(StrEnum):
    """Documentどうしの明示的関係。推測で設定しない(Docstring「Actual
    Observed vs Confirmed Relationship」参照)。`UNKNOWN`は「関係がある
    ことは確認できたが種別は確認できない」場合に使う(関係の存在自体が
    未確認の場合はRelationship Recordを作らない)。"""

    CORRECTS = "CORRECTS"
    RESTATES = "RESTATES"
    REPLACES = "REPLACES"
    REFERENCES = "REFERENCES"
    RELATED_TO = "RELATED_TO"
    UNKNOWN = "UNKNOWN"


class DuplicateRelationKind(StrEnum):
    """Deduplicationの最小基盤(Phase4B-1)。同じTitle/Date/会社というだけの
    heuristic判定は行わない(`normalize.find_same_source_document_id_signals`/
    `find_exact_content_duplicate_groups`のDocstring参照)。TDnet/EDINET/
    Company IRの同一Eventへの束ね(Event Clustering)は将来Phaseへ延期。"""

    EXACT_CONTENT_DUPLICATE = "EXACT_CONTENT_DUPLICATE"
    SAME_SOURCE_DOCUMENT_ID = "SAME_SOURCE_DOCUMENT_ID"
    UNKNOWN = "UNKNOWN"


@dataclass(kw_only=True, frozen=True)
class DisclosureAttachment:
    """Disclosure Document 1件に付随するAttachment 1件のメタデータ。

    Phase4B-1は実Downloadを行わないため、`content_hash`は通常`None`
    (Fileの実体を取得していない限りHash化できない)。`source_locator`は
    URL等の不透明な参照文字列として保持するのみで、このLab自身が解決・
    取得することはない。
    """

    attachment_id: str
    document_internal_id: str
    source_attachment_id: str | None = None
    media_type: str | None = None
    attachment_kind: AttachmentKind = AttachmentKind.UNKNOWN
    filename: str | None = None
    source_locator: str | None = None
    retrieved_at: datetime
    content_hash: str | None = None
    raw_snapshot_ref: str | None = None
    is_primary: bool = False
    availability: AttachmentAvailability = AttachmentAvailability.METADATA_ONLY

    def __post_init__(self) -> None:
        if self.retrieved_at.tzinfo is None:
            raise ValueError("retrieved_at はtz-awareである必要があります")


@dataclass(kw_only=True, frozen=True)
class DisclosureDocument:
    """Disclosure Document 1件(Source非依存)。

    `market_public_at_basis`/`provider_available_at_basis`をそれぞれ独立に
    持つ(Fundamentals Phase4Aの`SourceVersion.availability_basis`は
    provider_available_at側1つのみだったが、Documentでは市場公表時刻自体の
    確からしさも別途追跡する必要があるため、意図的に分離した設計、D0045参照)。

    `provider_available_at`は実際の観測ログが無い限り`availability_basis
    =UNKNOWN`のまま保持し(`normalize._provider_available_at_and_basis`と
    同じ保守的方針、D0043)、`market_public_at`へFallbackしない。

    `source_version`はProvider側の不透明なVersion/Revision識別子
    (例: 開示番号)であり、これ自体からRevision Relationshipを推測しない
    (`DocumentRelationship`のみが確認済みの関係を表現する)。
    """

    internal_document_id: str
    source_document_id: str | None = None
    entity_id: str | None = None
    title: str
    document_kind: DocumentKind = DocumentKind.UNKNOWN
    originating_source: str | None = None
    delivery_provider: str | None = None
    market_public_at: datetime | None = None
    market_public_at_basis: AvailabilityBasis = AvailabilityBasis.UNKNOWN
    provider_available_at: datetime | None = None
    provider_available_at_basis: AvailabilityBasis = AvailabilityBasis.UNKNOWN
    retrieved_at: datetime
    source_version: str | None = None
    raw_snapshot_ref: str | None = None
    language: str | None = None
    attachments: tuple[DisclosureAttachment, ...] = field(default_factory=tuple)
    provenance_id: str | None = None
    normalizer_version: str = NORMALIZER_VERSION

    def __post_init__(self) -> None:
        if self.retrieved_at.tzinfo is None:
            raise ValueError("retrieved_at はtz-awareである必要があります")
        if self.market_public_at is not None and self.market_public_at.tzinfo is None:
            raise ValueError("market_public_at はtz-awareである必要があります")
        if self.provider_available_at is not None and self.provider_available_at.tzinfo is None:
            raise ValueError("provider_available_at はtz-awareである必要があります")


@dataclass(kw_only=True, frozen=True)
class DocumentRelationship:
    """2つのDisclosureDocument間の、確認済みの明示的関係。

    `basis`は必須(自由記述): なぜこの関係を確認済みと判断したか
    (例: "Provider側Metadataの`ReplacesDocId`Fieldで明示", "Userによる
    目視確認、2026-08-xx")を記録する監査証跡。Relationshipの存在自体が
    未確認の場合、このRecordを作らない(「関係があるかもしれない」という
    憶測はRecord化しない)。
    """

    relationship_id: str
    from_document_id: str
    to_document_id: str
    relationship_kind: DocumentRelationshipKind = DocumentRelationshipKind.UNKNOWN
    basis: str


@dataclass(kw_only=True, frozen=True)
class DuplicateSignal:
    """2つのDocument(または2つのRaw Row)が重複している可能性についての、
    確認済みの機械的Signal。Title/Date/会社が同じというだけでは生成しない
    (`normalize.py`参照)。あくまで「候補」であり、自動でどちらかを削除・
    非表示にする処理はPhase4B-1では行わない。"""

    document_a_id: str
    document_b_id: str
    relation_kind: DuplicateRelationKind
    basis: str
