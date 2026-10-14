"""`PositioningRecord`群からRevision管理(`lib.evidence.model.RevisionHistory`)を
構築する(Phase4C)。Source非依存: どのSourceでも共通の`series_id`グルーピング/
`SourceVersion`構築ロジックのみを持ち、Source固有のAvailability Semantics
(いつ利用可能になったと言えるか)は呼び出し側が`resolve_available_at`として
明示的に渡す(Source Integration Skill v1 SOURCE-001「Source固有Field意味論を
推測しない」の精神。normalize.py自身はどのSourceの`available_at`計算方法も
知らない)。

`Fundamentals`(`lib.fundamentals.normalize.build_revision_histories`)と同じ
Primitiveをそのまま再利用する(新しいVersioning機構は作らない、Phase4C要件§31)。
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import datetime

from lib.evidence.model import AvailabilityBasis, RevisionHistory, SourceVersion
from lib.positioning.model import PositioningRecord

AvailableAtResolver = Callable[[PositioningRecord], tuple[datetime, AvailabilityBasis]]


def build_revision_histories(
    records: Sequence[PositioningRecord],
    *,
    resolve_available_at: AvailableAtResolver,
) -> dict[str, RevisionHistory]:
    """`series_id`ごとにグルーピングし`RevisionHistory`を構築する。

    `supersedes_version_id`は常に`None`(=関係不明)のまま扱う
    (Fundamentalsと同じ理由: 公式仕様でRevision Relationshipが確定できない
    限り推測しない)。`RevisionHistory.as_of()`がavailability_basis/
    available_at基準で安全に「その時点で使えた最新Version」を選ぶため、
    明示的なsupersedes chainが無くても機能する。
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
            event_at=record.observation_end,
            published_at=record.market_public_at,
        )
        versions_by_series.setdefault(record.series_id, []).append(version)
    return {
        series_id: RevisionHistory(series_id=series_id, versions=tuple(versions))
        for series_id, versions in versions_by_series.items()
    }
