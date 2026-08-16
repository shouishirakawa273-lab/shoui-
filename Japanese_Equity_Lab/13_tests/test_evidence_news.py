"""Phase3D(D0040): News設計(Japan/Global分離・Dedup Semantics)のテスト。"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from lib.evidence.news import NewsCluster, NewsDedupRelation, NewsEvent, NewsScope, classify_news_relation, cluster_news
from lib.sources.catalog import PrimaryOrSecondary, SourceAuthorityClass, SourceMetadata


def _source(url: str, *, provider: str = "TestWire") -> SourceMetadata:
    return SourceMetadata(
        source_id="s1",
        source_type="NEWS",
        provider_name=provider,
        source_authority_class=SourceAuthorityClass.VERIFIED_SECONDARY,
        primary_or_secondary=PrimaryOrSecondary.SECONDARY,
        retrieved_at=datetime(2024, 1, 1, tzinfo=UTC),
        published_at=datetime(2024, 1, 1, tzinfo=UTC),
        available_at=datetime(2024, 1, 1, tzinfo=UTC),
        source_url=url,
    )


def _event(
    news_id: str,
    *,
    scope: NewsScope,
    published_at: datetime,
    headline: str,
    entities: tuple[str, ...] = (),
    event_type: str = "EARNINGS",
    url: str = "http://example.com/1",
) -> NewsEvent:
    return NewsEvent(
        news_id=news_id,
        published_at=published_at,
        scope=scope,
        country="JP" if scope == NewsScope.JAPAN else "US",
        event_type=event_type,
        entities=entities,
        source=_source(url),
        headline=headline,
    )


# --- Test 6: Japan News / Global Newsの分類 ---


def test_news_scope_distinguishes_japan_and_global() -> None:
    jp = _event("n1", scope=NewsScope.JAPAN, published_at=datetime(2024, 1, 1, tzinfo=UTC), headline="日本株関連ニュース")
    gl = _event("n2", scope=NewsScope.GLOBAL, published_at=datetime(2024, 1, 1, tzinfo=UTC), headline="Global market news")
    assert jp.scope == NewsScope.JAPAN
    assert gl.scope == NewsScope.GLOBAL
    assert jp.scope != gl.scope


def test_news_event_requires_tz_aware_published_at() -> None:
    with pytest.raises(ValueError, match="tz-aware"):
        NewsEvent(
            news_id="n1",
            published_at=datetime(2024, 1, 1),  # tz無し
            scope=NewsScope.JAPAN,
            country="JP",
            event_type="EARNINGS",
            source=_source("http://x/1"),
            headline="h",
        )


def test_news_event_confidence_must_be_in_unit_range() -> None:
    with pytest.raises(ValueError, match="0.0"):
        NewsEvent(
            news_id="n1",
            published_at=datetime(2024, 1, 1, tzinfo=UTC),
            scope=NewsScope.JAPAN,
            country="JP",
            event_type="EARNINGS",
            source=_source("http://x/1"),
            headline="h",
            confidence=1.5,
        )


# --- Test 7: Duplicate NewsのDeduplication(+ Dedup Semanticsの区別) ---


def test_classify_exact_duplicate_by_same_headline_and_url() -> None:
    a = _event(
        "n1", scope=NewsScope.JAPAN, published_at=datetime(2024, 1, 1, 9, tzinfo=UTC), headline="同じ見出し", url="http://a/1"
    )
    b = _event(
        "n2", scope=NewsScope.JAPAN, published_at=datetime(2024, 1, 1, 9, tzinfo=UTC), headline="同じ見出し", url="http://a/1"
    )
    assert classify_news_relation(a, b) == NewsDedupRelation.EXACT_DUPLICATE


def test_classify_syndicated_copy_by_same_headline_different_source_same_day() -> None:
    a = _event(
        "n1", scope=NewsScope.JAPAN, published_at=datetime(2024, 1, 1, 9, tzinfo=UTC), headline="共通配信記事", url="http://a/1"
    )
    b = _event(
        "n2", scope=NewsScope.JAPAN, published_at=datetime(2024, 1, 1, 12, tzinfo=UTC), headline="共通配信記事", url="http://b/1"
    )
    assert classify_news_relation(a, b) == NewsDedupRelation.SYNDICATED_COPY


def test_classify_same_event_cluster_preserves_contradictory_reporting() -> None:
    """独立に報じた別記事(見出し・論調が異なる)はSAME_EVENT_CLUSTERとし、削除しない。"""
    a = _event(
        "n1",
        scope=NewsScope.JAPAN,
        published_at=datetime(2024, 1, 1, 9, tzinfo=UTC),
        headline="A社決算、市場予想を上回る",
        entities=("7203",),
        url="http://a/1",
    )
    b = _event(
        "n2",
        scope=NewsScope.JAPAN,
        published_at=datetime(2024, 1, 1, 10, tzinfo=UTC),
        headline="A社決算、実態は減速との指摘も",
        entities=("7203",),
        url="http://b/1",
    )
    assert classify_news_relation(a, b) == NewsDedupRelation.SAME_EVENT_CLUSTER


def test_classify_distinct_for_unrelated_articles() -> None:
    a = _event("n1", scope=NewsScope.JAPAN, published_at=datetime(2024, 1, 1, tzinfo=UTC), headline="A社決算", entities=("7203",))
    b = _event(
        "n2", scope=NewsScope.GLOBAL, published_at=datetime(2024, 1, 5, tzinfo=UTC), headline="FOMC結果", entities=("FED",)
    )
    assert classify_news_relation(a, b) == NewsDedupRelation.DISTINCT


def test_cluster_news_keeps_all_member_events_even_when_exact_duplicate() -> None:
    """EXACT_DUPLICATEであっても記事情報そのものを削除しない(event_idsは全メンバーを保持)。"""
    a = _event(
        "n1", scope=NewsScope.JAPAN, published_at=datetime(2024, 1, 1, 9, tzinfo=UTC), headline="同じ見出し", url="http://a/1"
    )
    b = _event(
        "n2", scope=NewsScope.JAPAN, published_at=datetime(2024, 1, 1, 9, tzinfo=UTC), headline="同じ見出し", url="http://a/1"
    )
    clusters = cluster_news([a, b])
    assert len(clusters) == 1
    cluster = clusters[0]
    assert isinstance(cluster, NewsCluster)
    assert set(cluster.event_ids) == {"n1", "n2"}
    assert cluster.relation == NewsDedupRelation.EXACT_DUPLICATE


def test_cluster_news_does_not_merge_distinct_articles() -> None:
    a = _event("n1", scope=NewsScope.JAPAN, published_at=datetime(2024, 1, 1, tzinfo=UTC), headline="A社決算", entities=("7203",))
    b = _event(
        "n2", scope=NewsScope.GLOBAL, published_at=datetime(2024, 1, 5, tzinfo=UTC), headline="FOMC結果", entities=("FED",)
    )
    clusters = cluster_news([a, b])
    assert len(clusters) == 2
    assert {frozenset(c.event_ids) for c in clusters} == {frozenset({"n1"}), frozenset({"n2"})}
