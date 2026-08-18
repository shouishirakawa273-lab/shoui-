"""Japan News Data Foundation(Phase4E-2): 日本語Newsの記事MetadataをPIT-safe/
provenance-preserving/reproducibleな形で表現する。

## Data Foundationまで、Event/Sentiment/Investment Conclusionは作らない

News Article != Fact != Event != Investment Conclusion(Phase4E-2要件§2/§3)。
`NewsArticleRecord`が保持するのは「この記事がこの見出しで公開された」という
Metadataのみであり、本文からのEvent抽出(決算Beat/M&A/Guidance変更等)・
Sentiment判定(Positive/Negative/Bullish/Bearish)はこのModuleのいずれの
Functionも生成しない(Phase4E-2要件§23/§24)。

## `lib.evidence.news.NewsEvent`との境界(重要、既存Phase3D Scaffoldとの関係)

Phase3D由来の`lib.evidence.news.NewsEvent`は、既に`event_type`(必須Field)・
`entities`/`affected_sectors`/`affected_codes`・`confidence`を持つ、**Event
抽出後**を前提としたSchemaである(そのModule Docstring自身が「News Feed ->
Metadata ingest -> Deduplication -> **Event extraction** -> ... -> Relevant
Retrieval」というPipelineの後半を担うと明記している)。また`classify_news_
relation()`は見出し正規化のみでEXACT_DUPLICATE/SYNDICATED_COPYを**自動**
判定する——これはPhase4E-2要件§28(「Headline Similarity Is Not Duplicate」、
見出し類似度だけでのDuplicate判定は禁止)より緩い基準である。

したがってこのRoundでは`lib.evidence.news.NewsEvent`を再利用・拡張せず
(既存Test`13_tests/test_evidence_news.py`も無変更のまま)、`lib/news/`を
**その手前の層(Metadata Ingest層)**として新設する: `NewsArticleRecord`は
`event_type`を持たず、`lib.news.normalize`のDuplicate検出はSafe(構造的に
確認可能)なSignalのみを返し、`NewsDedupRelation`のような自動Cluster化は
行わない。将来、`lib/news/`のOutputを`lib.evidence.news.NewsEvent`へ変換する
Layerが必要になった場合は別Roundで設計する(このRoundでは着手しない)。

## Article Identity(URLだけをIdentityにしない)

`source_native_id`(Source自身が付与する記事ID)が確認できる場合はこれを
優先する。`canonical_url`は参照用のFieldであり、Identity判定には使わない
(同じ記事がURL変更・Mobile URL・転載URL・Archive URLで複数存在しうる、
Phase4E-2要件§11)。

## Published Time != Provider Availability != Retrieved Time != Event Time

`published_at`(Sourceが記事に付与する公開時刻)・`provider_available_at`
(このLabがこのSource経由で実際に参照可能になった時刻)・`retrieved_at`
(このLabが実際に取得した時刻、Observed Safe Availability Timestamp)は
別概念であり混同しない(D0049/D0050と同じ原則、Disclosuresの`market_
public_at`/`provider_available_at`/`retrieved_at`分離を踏襲)。記事本文に
「昨日発表した」等の言及があっても、それは記事のEvent Time(出来事の発生
時刻)であり、`published_at`(記事自体の公開時刻)とは別概念である——本文
からのEvent Time抽出はこのRoundでは行わない(Phase4E-2要件§15)。

`published_at`はSourceが確認済みの正確なTimestamp(tz-aware)を渡した場合
のみ設定する(Disclosuresの`market_public_at`と同じPattern)。Sourceが日付
のみを提供する場合、時刻を推測せず`published_date`のみを設定し
`published_at`は`None`のままとする(Phase4E-2要件§12)。TimezoneがSourceで
明示されない場合もUTC/JSTへの変換を推測しない(tz-naiveなDatetimeの
Construction自体を拒否する、既存Patternと同じ)。

## Update/Correction(推測しない)

`updated_at`はSourceが明示的に確認済みのUpdate/Correction Timestampを
提供した場合のみ設定する(Phase4E-2要件§16)。同一URLの本文が後から変わる
ことは`updated_at`の根拠にならない(Mutable URL Problem、Phase4E-2要件
§17)——Raw Snapshotの変化はRawSnapshotStoreのAppend-only保存とHash比較で
検出できるが、それ自体を「Revisionが確認された」とは自動的に解釈しない
(RAW-002原則と同じ)。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum

from lib.evidence.model import AvailabilityBasis


class ContentAvailability(StrEnum):
    """本文保存の状態(Phase4E-2要件§19/§30)。Sourceの利用規約・Copyright上、
    全文保存が許可されない/未確認の場合に`FULL_TEXT`を主張しない。"""

    FULL_TEXT = "FULL_TEXT"
    HEADLINE_ONLY = "HEADLINE_ONLY"
    METADATA_ONLY = "METADATA_ONLY"
    REFERENCE_ONLY = "REFERENCE_ONLY"
    UNKNOWN = "UNKNOWN"


class NewsDuplicateRelationKind(StrEnum):
    """Safeに確認できるDuplicate Signalのみ(Phase4E-2要件§28)。見出し類似度・
    URL類似度・時刻近接は`Potential`扱いであり、このEnumのMemberとしては
    表現しない(このModuleは自動Same-article判定を行わない設計であるため、
    ここには「確認済み」の関係のみを列挙する、`lib.disclosures.model.
    DuplicateRelationKind`と同型の設計判断)。"""

    SAME_SOURCE_NATIVE_ID = "SAME_SOURCE_NATIVE_ID"
    EXACT_RAW_CONTENT_DUPLICATE = "EXACT_RAW_CONTENT_DUPLICATE"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class NewsDuplicateSignal:
    """2件の`NewsArticleRecord`が重複している可能性についての、確認済みの
    機械的Signal(あくまで候補、自動でどちらかを削除・非表示にしない、
    `lib.disclosures.model.DuplicateSignal`と同型)。"""

    article_a_id: str
    article_b_id: str
    relation_kind: NewsDuplicateRelationKind
    basis: str


@dataclass(kw_only=True, frozen=True)
class NewsArticleRecord:
    """News記事1件のMetadata(Phase4E-2)。

    `internal_article_id`はこのLab内部の一意識別子(必須)。`source_native_id`
    はSource自身が付与するID(確認できる場合のみ、Article Identityの優先
    候補)。`canonical_url`は参照用のみでIdentityには使わない。

    `entity_id`はSourceが構造化されたEntity識別子(会社Code等)を提供した
    場合のみ設定する。記事の見出し・本文からの会社名Text Matchingでは設定
    しない(曖昧な場合は`None`のまま、Phase4E-2要件§21)——見出しText由来の
    Entity推定はEvent抽出と同種のInferenceであり、このRoundのScope外。
    """

    internal_article_id: str
    source_native_id: str | None = None
    source_id: str
    headline: str
    language: str | None = None
    canonical_url: str | None = None
    published_date: date | None = None
    published_at: datetime | None = None
    published_at_basis: AvailabilityBasis = AvailabilityBasis.UNKNOWN
    provider_available_at: datetime | None = None
    provider_available_at_basis: AvailabilityBasis = AvailabilityBasis.UNKNOWN
    retrieved_at: datetime
    updated_at: datetime | None = None
    content_availability: ContentAvailability = ContentAvailability.UNKNOWN
    raw_snapshot_ref: str | None = None
    entity_id: str | None = None
    source_field: str | None = None
    normalizer_version: str
    provenance_id: str | None = None

    def __post_init__(self) -> None:
        if not self.internal_article_id:
            raise ValueError("internal_article_id は空にできません")
        if not self.source_id:
            raise ValueError("source_id は空にできません")
        if not self.headline:
            raise ValueError("headline は空にできません")
        if self.retrieved_at.tzinfo is None:
            raise ValueError("retrieved_at はtz-awareである必要があります")
        if self.published_at is not None and self.published_at.tzinfo is None:
            raise ValueError("published_at はtz-awareである必要があります(日付のみの場合はpublished_dateを使うこと)")
        if self.published_at is None and self.published_at_basis != AvailabilityBasis.UNKNOWN:
            raise ValueError("published_atが無いのにpublished_at_basisをUNKNOWN以外にはできません")
        if self.provider_available_at is not None and self.provider_available_at.tzinfo is None:
            raise ValueError("provider_available_at はtz-awareである必要があります")
        if self.provider_available_at is None and self.provider_available_at_basis != AvailabilityBasis.UNKNOWN:
            raise ValueError("provider_available_atが無いのにprovider_available_at_basisをUNKNOWN以外にはできません")
        if self.updated_at is not None and self.updated_at.tzinfo is None:
            raise ValueError("updated_at はtz-awareである必要があります")
