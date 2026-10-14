"""As-of Macro View(Phase4D): decision_at時点で利用可能だったMacro Metricの
みを返す。

外部API取得と分析を分離する(D0042「Backtest/Experimentの完全Offline原則」)。
この関数は事前に構築済みの`RevisionHistory`(`lib.macro.normalize.
build_revision_histories()`)だけを受け取り、一切のNetwork Access・Current
API Callを行わない。同じsnapshot・同じparams・同じas_ofなら常に同じ結果を
返す(Determinism、Phase4D要件§27)。

未来のRelease・未来のRevisionを絶対に含めない(`RevisionHistory.as_of()`が
`available_at`基準でフィルタする)。現在の最新Revised Valueを過去のas_ofへ
遡って適用しない(Current-state Leakage禁止、Phase4D要件§17)。Monthly
SeriesをDaily Seriesへ補間する処理はこのLayerでは行わない。
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime

from lib.evidence.model import RevisionHistory, SourceVersion


def macro_as_of(
    revision_histories: Mapping[str, RevisionHistory],
    decision_at: datetime,
    *,
    include_unknown_availability: bool = False,
) -> dict[str, SourceVersion | None]:
    """series_id -> decision_at時点で利用可能な最新`SourceVersion`(無ければ`None`)。

    `include_unknown_availability`は既定`False`(安全側): Availability Basisが
    `UNKNOWN`のVersionは既定で除外される(`RevisionHistory.as_of()`と同じ
    既定Behavior、Phase4D要件§12「UNKNOWNへのUnsafe Fallback禁止」)。
    """
    if decision_at.tzinfo is None:
        raise ValueError("decision_at はtz-awareである必要があります")
    return {
        series_id: history.as_of(decision_at, include_unknown_availability=include_unknown_availability)
        for series_id, history in revision_histories.items()
    }
