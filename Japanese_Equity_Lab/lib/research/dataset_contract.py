"""Phase5 v1: Dataset Contract。

**目的**: 1つのExperimentが「どのデータを、どう取得し、どうPIT整合させ、
どう欠損/コーポレートアクション/上場廃止を扱い、Feature/Targetをどう
計算したか」を実行前に文章として固定する(Phase5 v1要件§13-18)。

Dataset Contract自体はデータそのものを保持しない(データの取得元・
取得方法・PIT機構・調整方法などの**手順の記述**のみを保持する)。実際の
データ取得・PIT適用は既存の`lib.universe`(PIT Universe)・
`lib.point_in_time.PointInTimeRecord`・Phase3A Corporate Action調整機構
(`lib.backtest.engine`の`PriceHistorySource`経由)がそのまま担う。この
ModuleはBacktest Engineを新規に作らず、それらの機構を「どう使うか」を
宣言する契約書に過ぎない。

`contract_hash()`は、同じContract定義から同じHashが得られることを保証し、
`Experiment.dataset_contract_hash`(`lib.schemas.experiment`)へ記録される
再現性メタデータの一部として使う。
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import date

_CONTRACT_FIELDS = (
    "source",
    "snapshot_reference",
    "date_range_start",
    "date_range_end",
    "universe_mechanism",
    "pit_mechanism",
    "adjustment_method",
    "missing_handling",
    "corporate_action_handling",
    "delisting_handling",
    "liquidity_availability",
    "feature_computation",
    "target_computation",
)


@dataclass(kw_only=True, frozen=True)
class DatasetContract:
    """1つのExperimentが従うべきデータ取得・PIT整合手順の宣言。"""

    dataset_contract_id: str
    source: str
    snapshot_reference: str
    date_range_start: date
    date_range_end: date
    universe_mechanism: str
    pit_mechanism: str
    adjustment_method: str
    missing_handling: str
    corporate_action_handling: str
    delisting_handling: str
    liquidity_availability: str
    feature_computation: str
    target_computation: str
    notes: str = ""
    forbidden_capabilities: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not self.dataset_contract_id:
            raise ValueError("dataset_contract_id は空にできません")
        if self.date_range_start > self.date_range_end:
            raise ValueError("date_range_start は date_range_end 以前である必要があります")
        for name in _CONTRACT_FIELDS:
            if name in ("date_range_start", "date_range_end"):
                continue
            if not getattr(self, name):
                raise ValueError(f"{name} は空にできません(Phase5 v1要件§13-18)")

    def contract_terms(self) -> dict[str, object]:
        return {name: getattr(self, name) for name in _CONTRACT_FIELDS}

    def contract_hash(self) -> str:
        canonical = json.dumps(self.contract_terms(), sort_keys=True, ensure_ascii=False, default=str)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


__all__ = ["DatasetContract"]
