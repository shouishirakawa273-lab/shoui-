"""As-of View for `DisclosureDocument`(Phase4B-1、D0045)。

**設計上の重要な違い(Fundamentals`fundamentals_as_of()`との比較)**: Fundamentalsの
`FundamentalMetric`は「同じ指標の異なる時点の値」がSeriesを構成し、`as_of()`は
そのSeriesの「その時点で最新のVersion」を1件返す(Latest-wins)。一方
DisclosureDocumentは、それぞれが独立した意味を持つ文書であり、同じ会社の
複数の文書が同時に「見えている」状態が正しい(古い文書が新しい文書に置き換わる
わけではない)。そのため`disclosures_as_of()`は「Latest-wins」ではなく、
「decision_at時点で利用可能な文書の集合(Set Filter)」を返す。

この違いはPIT安全性の原則(UNKNOWN Basisを既定で除外する、Fallbackしない、
未来の文書を漏らさない)を弱めるものではなく、Documentという概念の性質から
来る自然な設計選択である(D0045)。

外部呼び出しを一切持たない(`FrozenPitUniverseProvider`/`fundamentals_as_of()`
と同じOffline-by-construction設計、D0042)。
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from lib.disclosures.model import DisclosureDocument
from lib.evidence.model import AvailabilityBasis, AvailabilitySemantics


def disclosures_as_of(
    documents: Sequence[DisclosureDocument],
    decision_at: datetime,
    *,
    availability_semantics: AvailabilitySemantics = AvailabilitySemantics.PROVIDER_AVAILABLE_AT,
    include_unknown_availability: bool = False,
) -> list[DisclosureDocument]:
    """`decision_at`時点で利用可能な`DisclosureDocument`の集合を返す(Set Filter、
    Latest-winsではない)。

    - `MARKET_PUBLIC_AT`(A系統): `market_public_at`が確認済み(`None`でない)かつ
      `market_public_at <= decision_at`の文書のみを含む。
    - `PROVIDER_AVAILABLE_AT`(B系統、既定): `provider_available_at`が確認済みかつ
      `<= decision_at`かつ、既定では`market_public_at_basis`/`provider_
      available_at_basis`が`UNKNOWN`の文書を除外する(呼び出し側が明示的に
      `include_unknown_availability=True`とした場合のみ許容、Fundamentals
      Phase4Aの`RevisionHistory.as_of()`と同じ安全側デフォルト)。

    未来の文書(`decision_at`より後にしか利用可能でない文書)は結果に含まれない。
    単純な日付比較(`date()`同士の比較)は行わず、tz-aware `datetime`同士で
    比較する(同日でも時刻がdecision_atより後なら除外する、D0045)。
    """
    if decision_at.tzinfo is None:
        raise ValueError("decision_at はtz-awareである必要があります")

    result: list[DisclosureDocument] = []
    for document in documents:
        if availability_semantics == AvailabilitySemantics.MARKET_PUBLIC_AT:
            timestamp = document.market_public_at
            basis = document.market_public_at_basis
        else:
            timestamp = document.provider_available_at
            basis = document.provider_available_at_basis

        if timestamp is None:
            continue
        if timestamp > decision_at:
            continue
        if basis == AvailabilityBasis.UNKNOWN and not include_unknown_availability:
            continue
        result.append(document)
    return result


__all__ = ["disclosures_as_of"]
