"""`ConsensusRecord`群からRevision/Vintage管理(`lib.evidence.model.
RevisionHistory`)を構築する(Phase4E-4)。

Source非依存: `series_id`によるGroupingと`SourceVersion`構築のみを持ち、
Source固有のAvailability Semantics(いつ利用可能になったと言えるか)は
呼び出し側が`resolve_available_at`として明示的に渡す(`lib.macro.
normalize`/`lib.positioning.normalize`と同じ設計)。

`lib.macro.normalize.build_revision_histories()`と意図的にほぼ同型の
小さな関数として書く(Cross-Capability抽象化は導入しない、Field名の
違い[`target_period_end` vs `reference_period_end`]により無理な共通化は
かえって複雑になるという既存判断、D0057関連の議論と同じ理由)。

**`is_correction`は常に`False`のまま扱う(Phase4E-4要件§32、Forecast
Evolution != Correction)**: Vintage間の推移(100→105→103)はAnalystの
見解更新であり、Sourceが明示的にCorrectionと述べない限り訂正として
扱わない(EVIDENCE-003原則、`lib.macro.normalize`/`lib.positioning.
normalize`と同じ扱い)。
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import datetime

from lib.consensus.model import ConsensusRecord
from lib.evidence.model import AvailabilityBasis, RevisionHistory, SourceVersion

AvailableAtResolver = Callable[[ConsensusRecord], tuple[datetime, AvailabilityBasis]]


def build_revision_histories(
    records: Sequence[ConsensusRecord],
    *,
    resolve_available_at: AvailableAtResolver,
) -> dict[str, RevisionHistory]:
    """`series_id`ごとにグルーピングし`RevisionHistory`を構築する。

    複数Vintageは、同一`series_id`に対する複数`SourceVersion`として自然に
    表現される。`RevisionHistory.as_of()`がavailability_basis/available_at
    基準で「その時点で観測可能だった最新Vintage」を正しく選ぶため、明示的な
    supersedes chainが無くても安全に機能する(Fundamentals/Positioning/
    Macroと同じ設計判断)。
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
            event_at=record.target_period_end,
            published_at=record.published_at,
        )
        versions_by_series.setdefault(record.series_id, []).append(version)
    return {
        series_id: RevisionHistory(series_id=series_id, versions=tuple(versions))
        for series_id, versions in versions_by_series.items()
    }


__all__ = ["AvailableAtResolver", "build_revision_histories"]
