"""`GlobalMarketRecord`群からRevision管理(`lib.evidence.model.
RevisionHistory`)を構築する(Phase4E-1)。Source非依存: `lib.positioning.
normalize`/`lib.macro.normalize`と同じ設計(`series_id`グルーピング+
呼び出し側が渡す`resolve_available_at`Callback)を踏襲する。3つの
Capability(Positioning/Macro/Global Market)でほぼ同型の小さな関数が
独立して存在することになるが、これはPhase4C/4D双方のskeptic-reviewer
Reviewを経て「Field名がCapability間で異なるため、無理なProtocol抽象化は
Premature Generalization」と判断済みの、意図した設計判断である
(DECISIONS.md D0054/D0055参照)。
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import datetime

from lib.evidence.model import AvailabilityBasis, RevisionHistory, SourceVersion
from lib.global_market.model import GlobalMarketRecord

AvailableAtResolver = Callable[[GlobalMarketRecord], tuple[datetime, AvailabilityBasis]]


def build_revision_histories(
    records: Sequence[GlobalMarketRecord],
    *,
    resolve_available_at: AvailableAtResolver,
) -> dict[str, RevisionHistory]:
    """`series_id`ごとにグルーピングし`RevisionHistory`を構築する。

    `series_id`が`session_date`を含まない場合、異なるSessionのRecordが
    同一Seriesへcollapseし、`global_market_as_of()`はより新しい
    `available_at`を持つSessionの値しか返さなくなる(Macro Phase4Dの
    `series_id`設計原則と同じ、`lib.global_market.model`Docstring参照)。
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
            event_at=record.session_date,
            published_at=record.market_public_at,
        )
        versions_by_series.setdefault(record.series_id, []).append(version)
    return {
        series_id: RevisionHistory(series_id=series_id, versions=tuple(versions))
        for series_id, versions in versions_by_series.items()
    }
