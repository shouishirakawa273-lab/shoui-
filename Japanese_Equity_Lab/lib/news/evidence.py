"""NewsArticleRecordからEvidenceを作る(Phase4E-2)。

**Core Principleの再確認**: 作れるのは記事公開というFACTのみ(例:「PR TIMES
が2026-08-18に『(見出し)』を公開した」)。記事本文の主張・関係者コメント・
「〜とみられる」等の推測表現(Claim)は、このPhaseでは一切FACTへ変換しない
(Article Claim != Confirmed Fact、Phase4E-2要件§22)。Sentiment(Positive/
Negative/Bullish/Bearish)・Event分類(決算Beat/M&A等)はここでは一切生成
しない(Phase4E-2要件§23/§24)。

**`EvidenceType.FACT`固定についての注記(skeptic-reviewer Finding、
Phase4E-2、MEDIUM)**: `lib.evidence.model`のEvidence Type定義は、FACT
(例:「TDnetでの会社予想修正」)とCLAIM(例:「会社IRの『需要は堅調』という
発言」、発言の存在自体はFACTだが内容の真偽は別)を明確に区別する。この
関数がFACTとするのは**「この見出しの記事がこのSourceから公開された」
という発行事実そのもの**であり(`lib.disclosures.evidence.disclosure_
document_to_evidence()`が文書Titleに対して行うのと同じMeta-level FACT
の扱い)、`headline`(見出し)そのものの内容——特にPR TIMES等
`COMPANY_PRIMARY`(発行企業自身)Sourceの場合、見出しが企業の宣伝的な
表現(例:「業績絶好調」)を含みうる——を検証済みの事実として主張して
いるわけではない。現時点ではSourceが未実装のため、この区別は理論上の
懸念に留まるが、将来PR TIMES等`COMPANY_PRIMARY` Sourceの実Adapterを
実装しEvidenceを実際に消費する段階になった時点で、`headline`自体の
内容が推測・宣伝的表現を含む場合の扱い(CLAIM相当への分離要否)を
再検討する必要がある(Known Limitation、`JAPAN_NEWS_ARCHITECTURE.md`
参照)。

**D0057との境界(最重要、必読)**: この関数が返す`EvidenceRecord`は
`lib.evidence.retrieval.filter_usable_at()`等のEvidence経路PIT判定に
技術的には使用可能だが、**このRoundではBacktest/Decision Engineへ一切
接続しない**(Phase4E-2要件§25)。D0057(ARCHITECTURE_GAP、Validation
Backlog #21)が確認した通り、Evidence経路の`available_at`(常に`retrieved_
at`基準)と`lib.news.view.news_as_of()`のCanonical Availability Semantics
は独立した推定戦略であり、両者を統合する設計判断はこのRoundでは行わない。
"""

from __future__ import annotations

from datetime import datetime

from lib.evidence.model import AvailabilityBasis, DataLayer, EvidenceRecord, EvidenceType
from lib.news.model import NewsArticleRecord
from lib.sources.catalog import DataCapability, PrimaryOrSecondary, SourceAuthorityClass, SourceMetadata


def news_article_to_evidence(
    article: NewsArticleRecord,
    *,
    source_authority_class: SourceAuthorityClass,
    originating_source: str,
    delivery_provider: str,
) -> EvidenceRecord:
    """記事が公開されたという事実のみをFACTとして記述する(本文の解釈を
    加えない)。

    `source.available_at`は`lib.disclosures.evidence.disclosure_document_to_
    evidence()`と同じ優先順位で決定する(D0049/D0050 PIT Bugfix方針の
    踏襲): (1) `provider_available_at`が確認済み(`provider_available_at_
    basis != AvailabilityBasis.UNKNOWN`)であればそれを使う、(2) 確認でき
    なければ`article.retrieved_at`(Observed Safe Availability Timestamp、
    正確なProvider Availabilityそのものではない下限)を使う。**`published_
    at`へは決してFallbackしない**。
    """
    if article.provider_available_at is not None and article.provider_available_at_basis != AvailabilityBasis.UNKNOWN:
        available_at: datetime = article.provider_available_at
    else:
        available_at = article.retrieved_at

    published_display = (
        article.published_at.isoformat()
        if article.published_at is not None
        else (article.published_date.isoformat() if article.published_date is not None else "取得不可")
    )
    content = f"{article.source_id}: 「{article.headline}」を公開(published={published_display})"
    source = SourceMetadata(
        source_id=article.internal_article_id,
        source_type="NEWS_ARTICLE",
        provider_name=article.source_id,
        source_authority_class=source_authority_class,
        primary_or_secondary=PrimaryOrSecondary.PRIMARY,
        retrieved_at=article.retrieved_at,
        published_at=article.published_at,
        available_at=available_at,
        originating_source=originating_source,
        delivery_provider=delivery_provider,
        provenance_id=article.provenance_id,
    )
    related_codes = () if article.entity_id is None else (article.entity_id,)
    return EvidenceRecord(
        evidence_id=f"EVID_NEWS_{article.internal_article_id}",
        evidence_type=EvidenceType.FACT,
        layer=DataLayer.NORMALIZED,
        capability=DataCapability.NEWS,
        content=content,
        source=source,
        related_codes=related_codes,
        provenance_id=article.provenance_id,
    )


__all__ = ["news_article_to_evidence"]
