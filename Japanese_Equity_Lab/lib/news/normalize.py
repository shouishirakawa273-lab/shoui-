"""News記事のDuplicate検出(Phase4E-2)。Safeに確認できるSignalのみを返す
(見出し類似度・URL類似度・時刻近接からの自動Same-article判定は行わない、
Phase4E-2要件§28「Headline Similarity Is Not Duplicate」)。

`lib.disclosures.normalize.find_same_source_document_id_signals()`/
`find_exact_content_duplicate_groups()`と同型の設計(Source Integration
Skill v1の精神を踏襲、意図的にCode共有はしない——`NewsArticleRecord`と
`DisclosureDocument`はField名が異なり、Positioning/Macro/Global Marketの
`resolve_available_at`と同じ理由でCross-Capability抽象化を見送る)。
"""

from __future__ import annotations

import itertools
from collections.abc import Mapping, Sequence

from lib.news.model import NewsArticleRecord, NewsDuplicateRelationKind, NewsDuplicateSignal
from lib.reproducibility import hash_json_safe


def find_same_source_native_id_signals(articles: Sequence[NewsArticleRecord]) -> list[NewsDuplicateSignal]:
    """同一Source内で同一`source_native_id`を持つ複数`NewsArticleRecord`を
    Duplicate候補として検出する。**Headline/PublishedDate/Entityが同じ
    というだけでは検出しない**(それらはこの関数の入力に一切使われない、
    意図的な構造上の制約)。

    **`source_id`でScopeする(skeptic-reviewer Finding、Phase4E-2、
    MEDIUM)**: `source_native_id`のみでGroupingすると、異なるSource
    (例: JPX News ReleasesとFSA報道発表資料)がたまたま同じ`source_
    native_id`文字列を使っていた場合、無関係な記事同士を誤ってDuplicate
    Signalとして検出してしまう。4候補中`source_native_id`のGlobal一意性が
    確認できたSourceは無い(PR TIMESの`{company_id}.{release_seq}`のみ
    部分的に示唆、JPX/FSA/METIはいずれも未確認)。`NewsArticleRecord.
    source_id`は`__post_init__`で非空を必須とする既存Fieldであり、追加
    Cost無く安全側に倒せる。
    """
    by_source_and_native_id: dict[tuple[str, str], list[str]] = {}
    for article in articles:
        # 空文字列もNoneと同様に除外する(disclosures.normalizeと同じ理由:
        # 「IDが確認できない」という共通点だけで無関係な記事間にDuplicate
        # Signalを誤生成しないため)。
        if article.source_native_id:
            key = (article.source_id, article.source_native_id)
            by_source_and_native_id.setdefault(key, []).append(article.internal_article_id)

    signals: list[NewsDuplicateSignal] = []
    for (source_id, native_id), internal_ids in by_source_and_native_id.items():
        if len(internal_ids) < 2:
            continue
        for article_a, article_b in itertools.combinations(sorted(internal_ids), 2):
            signals.append(
                NewsDuplicateSignal(
                    article_a_id=article_a,
                    article_b_id=article_b,
                    relation_kind=NewsDuplicateRelationKind.SAME_SOURCE_NATIVE_ID,
                    basis=f"source_id={source_id}, source_native_id={native_id}",
                )
            )
    return signals


def find_exact_raw_content_duplicate_groups(payload: Sequence[Mapping[str, object]]) -> dict[str, list[int]]:
    """Raw Payload内で、行全体のContent Hash(`lib.reproducibility.
    hash_json_safe`を再利用、独自Hash実装はしない)が完全一致する行のIndexを
    グルーピングする(例: Pagination境界での重複取得を検出する用途)。Hashが
    1件しかないGroupは返さない(重複候補のみ)。Headlineや日付だけを見た
    Heuristic判定ではなく、行全体の完全一致のみを対象とする。
    """
    groups: dict[str, list[int]] = {}
    for i, row in enumerate(payload):
        content_hash = hash_json_safe(row)
        groups.setdefault(content_hash, []).append(i)
    return {content_hash: idxs for content_hash, idxs in groups.items() if len(idxs) > 1}
