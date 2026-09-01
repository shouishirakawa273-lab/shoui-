"""As-of View for `NewsArticleRecord`(Phase4E-2)。

`lib.disclosures.view.disclosures_as_of()`と同じ設計上の理由により
「Latest-wins」ではなく「decision_at時点で利用可能な記事の集合(Set
Filter)」を返す: News記事はそれぞれ独立した意味を持ち、同じ会社についての
複数記事が同時に「見えている」状態が正しい(古い記事が新しい記事に置き
換わるわけではない、Macro/Positioning/Global MarketのSeries的なLatest-wins
とは性質が異なる)。

外部呼び出しを一切持たない(`fundamentals_as_of()`/`disclosures_as_of()`/
`macro_as_of()`/`positioning_as_of()`/`global_market_as_of()`と同じ
Offline-by-construction設計、D0042)。

**D0057との境界(重要)**: この`news_as_of()`はCanonical Availability
Semantics(A系統`published_at`/B系統`provider_available_at`)のみを扱う
Pure Offline Viewである。Evidence経路(`lib.news.evidence.news_article_to_
evidence()`が生成する`EvidenceRecord.available_at`、常に`retrieved_at`
基準)とは別の推定戦略であり、D0057(ARCHITECTURE_GAP)が指摘した通り
両者は構造的に一致する保証が無い。このRoundはこの2経路を統合しない
(Backlog #21は維持したまま)。
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from lib.evidence.model import AvailabilityBasis, AvailabilitySemantics
from lib.news.model import NewsArticleRecord


def news_as_of(
    articles: Sequence[NewsArticleRecord],
    decision_at: datetime,
    *,
    availability_semantics: AvailabilitySemantics = AvailabilitySemantics.PROVIDER_AVAILABLE_AT,
    include_unknown_availability: bool = False,
) -> list[NewsArticleRecord]:
    """`decision_at`時点で利用可能な`NewsArticleRecord`の集合を返す(Set
    Filter、Latest-winsではない)。

    - `MARKET_PUBLIC_AT`(A系統): `published_at`が確認済み(`None`でない)かつ
      `published_at <= decision_at`の記事のみを含む。
    - `PROVIDER_AVAILABLE_AT`(B系統、既定): `provider_available_at`が確認済み
      かつ`<= decision_at`の記事のみを含む。

    **`published_at_basis`/`provider_available_at_basis`が`UNKNOWN`の記事は、
    A系統・B系統のどちらでも既定で除外する**(呼び出し側が明示的に`include_
    unknown_availability=True`とした場合のみ許容、既存Capability群と同じ
    安全側デフォルト)。`published_at`へのFallbackは行わない(未確認の
    provider_available_atをpublished_atで代用しない)。

    未来の記事(`decision_at`より後にしか利用可能でない記事)は結果に含まれ
    ない。単純な日付比較ではなく、tz-aware `datetime`同士で比較する。
    """
    if decision_at.tzinfo is None:
        raise ValueError("decision_at はtz-awareである必要があります")

    result: list[NewsArticleRecord] = []
    for article in articles:
        if availability_semantics == AvailabilitySemantics.MARKET_PUBLIC_AT:
            timestamp = article.published_at
            basis = article.published_at_basis
        else:
            timestamp = article.provider_available_at
            basis = article.provider_available_at_basis

        if timestamp is None:
            continue
        if timestamp > decision_at:
            continue
        if basis == AvailabilityBasis.UNKNOWN and not include_unknown_availability:
            continue
        result.append(article)
    return result


__all__ = ["news_as_of"]
