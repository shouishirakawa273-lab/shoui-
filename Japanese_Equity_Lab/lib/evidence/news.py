"""News設計: Japan News / Global Newsを明示的に分離しつつ、共通NewsEvent Schemaで扱う。

Newsを全件LLMへ投入する設計は禁止する。想定Pipelineは
News Feed -> Metadata ingest -> Deduplication -> Event extraction ->
Entity/Country/Sector Mapping -> Japanese Equity Relevance Scoring ->
Relevant Retrieval -> Deep Analysis であり、Phase3Dでは`NewsEvent` Schemaと
Deduplicationの土台までを実装する(Relevance Scoring自体のAI実装はPhase5/6)。

## News Dedup Semantics(D0040)

単純なDedupで記事を削除しない。以下を区別する。

- `EXACT_DUPLICATE`: 同一記事の重複取得(例: 同じURLを再取得した)。
- `SYNDICATED_COPY`: 同じ配信元記事が複数媒体に転載されたもの(内容はほぼ同一)。
- `SAME_EVENT_CLUSTER`: 同じ出来事を独立に報じた別記事(内容・論調が異なりうる)。
  Contradictory reporting(矛盾する報道)を保持するため、削除せずクラスタとして
  まとめるだけにとどめる。

`EXACT_DUPLICATE`のみ代表1件への圧縮を許容し、`SYNDICATED_COPY`/
`SAME_EVENT_CLUSTER`は全メンバーを保持する(要約・表示側でクラスタとして
まとめて見せることはできるが、個々の記事情報は失わない)。

将来的に、Global Event -> Economic Transmission -> Japanese Sector ->
Japanese Companyという伝播関係(例: 「US Data Center Capex増 -> 電力需要増 ->
変圧器需要増 -> 銅需要増 -> 日本の電気機器メーカー」)をSchema/Graph構造として
表現できることを想定するが、Phase3Dではこの推論自体は実装しない
(`NewsEvent.affected_sectors`/`affected_codes`は現時点では人手/将来Agentが
設定するプレースホルダとして持つのみ)。
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from lib.sources.catalog import SourceMetadata


class NewsScope(StrEnum):
    JAPAN = "JAPAN"
    GLOBAL = "GLOBAL"


@dataclass(kw_only=True, frozen=True)
class NewsEvent:
    news_id: str
    published_at: datetime
    scope: NewsScope
    country: str | None
    event_type: str
    entities: tuple[str, ...] = field(default_factory=tuple)
    affected_sectors: tuple[str, ...] = field(default_factory=tuple)
    affected_codes: tuple[str, ...] = field(default_factory=tuple)
    source: SourceMetadata
    headline: str
    summary: str | None = None
    confidence: float | None = None  # 0.0-1.0、未計算ならNone(推測で埋めない)
    provenance_id: str | None = None

    def __post_init__(self) -> None:
        if self.published_at.tzinfo is None:
            raise ValueError("published_at はtz-awareである必要があります")
        if self.confidence is not None and not (0.0 <= self.confidence <= 1.0):
            raise ValueError("confidence は0.0〜1.0の範囲である必要があります")

    @property
    def available_at(self) -> datetime:
        return self.source.available_at


class NewsDedupRelation(StrEnum):
    EXACT_DUPLICATE = "EXACT_DUPLICATE"
    SYNDICATED_COPY = "SYNDICATED_COPY"
    SAME_EVENT_CLUSTER = "SAME_EVENT_CLUSTER"
    DISTINCT = "DISTINCT"


def _normalize_headline(headline: str) -> str:
    return "".join(headline.split()).casefold()


def classify_news_relation(a: NewsEvent, b: NewsEvent) -> NewsDedupRelation:
    """2記事の関係を分類する簡易ヒューリスティック(D0040)。

    本格的な文章類似度判定ではなく、見出し正規化・発行時刻・entity重複による
    最小限の判定にとどめる(将来Phase5/6で高度化する余地を残す、過剰実装しない)。
    """
    if a.news_id == b.news_id:
        return NewsDedupRelation.EXACT_DUPLICATE

    norm_a, norm_b = _normalize_headline(a.headline), _normalize_headline(b.headline)
    same_headline = norm_a == norm_b
    same_source_url = a.source.source_url is not None and a.source.source_url == b.source.source_url

    if same_headline and same_source_url:
        return NewsDedupRelation.EXACT_DUPLICATE
    if same_headline and a.published_at.date() == b.published_at.date():
        return NewsDedupRelation.SYNDICATED_COPY

    shared_entities = set(a.entities) & set(b.entities)
    same_day = a.published_at.date() == b.published_at.date()
    if shared_entities and same_day and a.event_type == b.event_type:
        return NewsDedupRelation.SAME_EVENT_CLUSTER

    return NewsDedupRelation.DISTINCT


@dataclass(frozen=True)
class NewsCluster:
    """`SAME_EVENT_CLUSTER`/`SYNDICATED_COPY`/`EXACT_DUPLICATE`でまとめた記事群。

    `relation`はクラスタ内で観測された最も強い関係(EXACT_DUPLICATE >
    SYNDICATED_COPY > SAME_EVENT_CLUSTER)。`event_ids`は全メンバーを保持する
    (`EXACT_DUPLICATE`であっても、削除ではなくクラスタとして表現し、代表IDの
    選択は表示側の責務とする)。
    """

    cluster_id: str
    relation: NewsDedupRelation
    event_ids: tuple[str, ...]


_RELATION_STRENGTH = {
    NewsDedupRelation.EXACT_DUPLICATE: 3,
    NewsDedupRelation.SYNDICATED_COPY: 2,
    NewsDedupRelation.SAME_EVENT_CLUSTER: 1,
    NewsDedupRelation.DISTINCT: 0,
}


def cluster_news(events: Sequence[NewsEvent]) -> tuple[NewsCluster, ...]:
    """記事群をクラスタにまとめる。`DISTINCT`な記事は単独クラスタになる。

    どの関係であっても記事そのものを削除しない(Contradictory reportingを保持する)。
    """
    n = len(events)
    parent = list(range(n))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i: int, j: int) -> None:
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[ri] = rj

    pair_relation: dict[tuple[int, int], NewsDedupRelation] = {}
    for i in range(n):
        for j in range(i + 1, n):
            relation = classify_news_relation(events[i], events[j])
            if relation != NewsDedupRelation.DISTINCT:
                pair_relation[(i, j)] = relation
                union(i, j)

    groups: dict[int, list[int]] = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(i)

    clusters: list[NewsCluster] = []
    for cluster_index, (_root, members) in enumerate(sorted(groups.items())):
        strongest: NewsDedupRelation = NewsDedupRelation.DISTINCT
        for a in range(len(members)):
            for b in range(a + 1, len(members)):
                key = (min(members[a], members[b]), max(members[a], members[b]))
                relation = pair_relation.get(key, NewsDedupRelation.DISTINCT)
                if _RELATION_STRENGTH[relation] > _RELATION_STRENGTH[strongest]:
                    strongest = relation
        clusters.append(
            NewsCluster(
                cluster_id=f"CLUSTER_{cluster_index}",
                relation=strongest,
                event_ids=tuple(events[i].news_id for i in members),
            )
        )
    return tuple(clusters)
