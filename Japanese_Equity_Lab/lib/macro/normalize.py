"""`MacroRecord`群からRevision/Vintage管理(`lib.evidence.model.RevisionHistory`)
を構築する(Phase4D)。Source非依存: どのSourceでも共通の`series_id`グルーピング
/`SourceVersion`構築ロジックのみを持ち、Source固有のAvailability Semantics
(いつ利用可能になったと言えるか)は呼び出し側が`resolve_available_at`として
明示的に渡す(`lib.positioning.normalize`と同じ設計、Source Integration
Skill v1 SOURCE-001の精神。normalize.py自身はどのSourceの`available_at`
計算方法も知らない)。

`lib.fundamentals.normalize.build_revision_histories()`/`lib.positioning.
normalize.build_revision_histories()`と同じPrimitiveをそのまま再利用する
(新しいVintage/Versioning機構は作らない、Phase4D要件§16)。意図的に、この
2つの既存実装とほぼ同型の小さな関数として書く(Positioning/Macroを跨いだ
汎用Protocol抽象化は導入しない — 各RecordのField名が微妙に異なる
[`observation_end` vs `reference_period_end`]ため、無理に共通化すると
かえって複雑になる、という判断)。

`supersedes_version_id`/`is_correction`は常に未設定のまま扱う(Vintage
関係をSourceが明示しない限り推測しない、EVIDENCE-003と同じ原則)。
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import datetime

from lib.evidence.model import AvailabilityBasis, RevisionHistory, SourceVersion
from lib.macro.model import MacroRecord

AvailableAtResolver = Callable[[MacroRecord], tuple[datetime, AvailabilityBasis]]


def build_revision_histories(
    records: Sequence[MacroRecord],
    *,
    resolve_available_at: AvailableAtResolver,
) -> dict[str, RevisionHistory]:
    """`series_id`ごとにグルーピングし`RevisionHistory`を構築する。

    複数Vintage(Preliminary/Revised/Final)は、同一`series_id`に対する
    複数`SourceVersion`として自然に表現される。`RevisionHistory.as_of()`が
    availability_basis/available_at基準で「その時点で使えた最新Version」を
    正しく選ぶため、明示的なsupersedes chainが無くても安全に機能する
    (Fundamentals/Positioningと同じ設計判断)。
    """
    versions_by_series: dict[str, list[SourceVersion]] = {}
    for record in records:
        available_at, availability_basis = resolve_available_at(record)
        if available_at.tzinfo is None:
            raise ValueError(
                f"record_id={record.record_id}: resolve_available_atが返したavailable_atはtz-awareである必要があります"
            )
        version = SourceVersion(
            source_record_id=record.series_id,
            source_version_id=record.record_id,
            value=record.raw_value if record.raw_value is not None else "",
            available_at=available_at,
            retrieved_at=record.retrieved_at,
            availability_basis=availability_basis,
            is_correction=False,
            event_at=record.reference_period_end,
            published_at=record.market_public_at,
        )
        versions_by_series.setdefault(record.series_id, []).append(version)
    return {
        series_id: RevisionHistory(series_id=series_id, versions=tuple(versions))
        for series_id, versions in versions_by_series.items()
    }
