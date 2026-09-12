"""As-of Global Market View(Phase4E-1): decision_at時点で利用可能だった
Global Market Metricのみを返す。

外部API取得と分析を分離する(D0042「Backtest/Experimentの完全Offline原則」)。
この関数は事前に構築済みの`RevisionHistory`(`lib.global_market.normalize.
build_revision_histories()`)だけを受け取り、一切のNetwork Access・Current
API Callを行わない。同じsnapshot・同じparams・同じas_ofなら常に同じ結果を
返す(Determinism、Phase4E-1要件§24)。

**Japan Decision-Time Leakage禁止(最重要、Phase4E-1要件§11)**: 日本株
Researchの`decision_at`から見て、その時刻までに実際に終了・観測可能
だったGlobal Market Dataのみ使える。`decision_at`は必ずtz-aware
(UTC/JST等)で渡し、`available_at`(`resolve_available_at`が返す、実際の
Market Close等をtz-aware/DST-safeに解決した値)との比較で判定する。
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime

from lib.evidence.model import RevisionHistory, SourceVersion


def global_market_as_of(
    revision_histories: Mapping[str, RevisionHistory],
    decision_at: datetime,
    *,
    include_unknown_availability: bool = False,
) -> dict[str, SourceVersion | None]:
    """series_id -> decision_at時点で利用可能な最新`SourceVersion`(無ければ`None`)。

    `decision_at`はどのTimezoneのtz-aware datetimeでも良い(Python
    datetime比較は内部的にUTCへ正規化される)。日本株Researchの
    `decision_at`(JST)とGlobal Marketの`available_at`(US Eastern等から
    解決)を直接比較できる。`include_unknown_availability`は既定`False`
    (安全側): Availability Basisが`UNKNOWN`のVersionは既定で除外される。
    """
    if decision_at.tzinfo is None:
        raise ValueError("decision_at はtz-awareである必要があります")
    return {
        series_id: history.as_of(decision_at, include_unknown_availability=include_unknown_availability)
        for series_id, history in revision_histories.items()
    }
