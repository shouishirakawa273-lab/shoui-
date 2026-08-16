"""Experiment Registry: 追記専用(append-only)でExperimentを記録する。

AIが多数の戦略を試した場合でも、良かったものだけを見せてはいけない。
generated/tested/rejected/pending/paper/validatedの分母を常に保存・集計する。
上書き・削除のAPIは意図的に提供しない(experiment_idの重複はエラーにする)。
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from lib.backtest.engine import BacktestMetrics, DataSplit
from lib.errors import AppendOnlyViolationError
from lib.schemas.experiment import Experiment, ExperimentStatus

# JSON Lines <-> dataclass の変換は実行時にしか型を検証できない(JSONにはenum/datetime/
# 整数キーが無いため)。ここだけ dict[str, Any] を使い、以降のコードはdataclass経由で
# 型付きに戻す。


def _experiment_to_dict(experiment: Experiment) -> dict[str, Any]:
    payload = asdict(experiment)
    payload["status"] = experiment.status.value
    payload["created_at"] = experiment.created_at.isoformat()
    payload["updated_at"] = experiment.updated_at.isoformat()
    if experiment.metrics is not None:
        payload["metrics"]["data_split"] = experiment.metrics.data_split.value
    return payload


def _metrics_from_dict(data: dict[str, Any] | None) -> BacktestMetrics | None:
    if data is None:
        return None
    d: dict[str, Any] = dict(data)
    d["data_split"] = DataSplit(d["data_split"])
    d["year_by_year_performance"] = {int(k): v for k, v in dict(d.get("year_by_year_performance") or {}).items()}
    return BacktestMetrics(**d)


def _experiment_from_dict(data: dict[str, Any]) -> Experiment:
    d: dict[str, Any] = dict(data)
    d["status"] = ExperimentStatus(d["status"])
    d["metrics"] = _metrics_from_dict(d.get("metrics"))
    d["created_at"] = datetime.fromisoformat(d["created_at"])
    d["updated_at"] = datetime.fromisoformat(d["updated_at"])
    return Experiment(**d)


class ExperimentRegistry:
    """JSON Lines形式で追記専用に記録するExperiment Registry。"""

    def __init__(self, storage_path: Path) -> None:
        self._storage_path = storage_path
        self._storage_path.parent.mkdir(parents=True, exist_ok=True)

    def record(self, experiment: Experiment) -> None:
        existing_ids = {e.experiment_id for e in self.all()}
        if experiment.experiment_id in existing_ids:
            raise AppendOnlyViolationError(f"experiment_id={experiment.experiment_id} は既に記録されています(上書き不可)")
        line = json.dumps(_experiment_to_dict(experiment), ensure_ascii=False)
        with self._storage_path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")

    def all(self) -> list[Experiment]:
        if not self._storage_path.exists():
            return []
        experiments = []
        with self._storage_path.open(encoding="utf-8") as f:
            for raw_line in f:
                line = raw_line.strip()
                if line:
                    experiments.append(_experiment_from_dict(json.loads(line)))
        return experiments

    def summary(self) -> dict[str, int]:
        """generated/tested/rejected/pending/paper/validatedの分母。"""
        counts = Counter(e.status.value for e in self.all())
        return {status.value: counts.get(status.value, 0) for status in ExperimentStatus}
