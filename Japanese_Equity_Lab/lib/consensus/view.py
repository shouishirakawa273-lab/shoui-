"""As-of Consensus View(Phase4E-4): decision_at時点でこのLabが観測可能
だったConsensus Vintageのみを返す。

外部API取得と分析を分離する(D0042「Backtest/Experimentの完全Offline
原則」)。この関数は事前に構築済みの`RevisionHistory`(`lib.consensus.
normalize.build_revision_histories()`)だけを受け取り、一切のNetwork
Access・Current API Callを行わない。同じsnapshot・同じparams・同じ
as_ofなら常に同じ結果を返す(Determinism、Phase4E-4要件§40)。

未来のVintageを絶対に含めない(`RevisionHistory.as_of()`が`available_at`
基準でフィルタする)。現在の最新Vintageを過去のas_ofへ遡って適用しない
(Current Consensus Leakage禁止、Phase4E-4要件§12)。

`series_id`が同一Consensus seriesについて「as_of時点でどのVintageが
見えるか」を決定論的に扱う(Phase4E-4要件§41)。**既知のCommon-Core
Limitation(RevisionHistory Tie-break、Phase4E-4要件§42)**: 同一
`available_at`を持つ複数`SourceVersion`が存在する場合の順序はInput
Order依存であり(Positioning/Macro/Global Marketと同じKnown Limitation)、
このRoundでは実Sourceでこのケースが具体的に発生しない限りCommon Coreを
変更しない。
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime

from lib.evidence.model import RevisionHistory, SourceVersion


def consensus_as_of(
    revision_histories: Mapping[str, RevisionHistory],
    decision_at: datetime,
    *,
    include_unknown_availability: bool = False,
) -> dict[str, SourceVersion | None]:
    """series_id -> decision_at時点で観測可能な最新Vintage(`SourceVersion`、
    無ければ`None`)。

    `include_unknown_availability`は既定`False`(安全側): Availability
    Basisが`UNKNOWN`のVintageは既定で除外される(`RevisionHistory.as_of()`
    と同じ既定Behavior、Unknown Provider Availability Fails Closed、
    Phase4E-4要件§4/CONS-004)。
    """
    if decision_at.tzinfo is None:
        raise ValueError("decision_at はtz-awareである必要があります")
    return {
        series_id: history.as_of(decision_at, include_unknown_availability=include_unknown_availability)
        for series_id, history in revision_histories.items()
    }


__all__ = ["consensus_as_of"]
