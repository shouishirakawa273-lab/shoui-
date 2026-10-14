"""Preregistration Registry: 追記専用(append-only)でPreregistrationを記録する。

`lib.registry.experiment_registry.ExperimentRegistry`と全く同じPattern
(JSON Lines、重複ID拒否、削除APIを提供しない)をPreregistration向けに
そのまま踏襲する。DRAFT状態のPreregistrationも記録できるが、`revise()`で
派生させた新しいPreregistrationは元のIDとは別のIDとして記録されるため、
過去のPreregistrationが上書きされることはない(Publication Bias防止、
Phase5 v1要件§45と同じ趣旨)。
"""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from lib.errors import AppendOnlyViolationError
from lib.research.preregistration import Preregistration, PreregistrationStatus


def _preregistration_to_dict(preregistration: Preregistration) -> dict[str, Any]:
    payload = asdict(preregistration)
    payload["status"] = preregistration.status.value
    payload["created_at"] = preregistration.created_at.isoformat()
    payload["updated_at"] = preregistration.updated_at.isoformat()
    for key in (
        "train_period_start",
        "train_period_end",
        "validation_period_start",
        "validation_period_end",
        "locked_test_period_start",
        "locked_test_period_end",
    ):
        payload[key] = getattr(preregistration, key).isoformat()
    return payload


def _preregistration_from_dict(data: dict[str, Any]) -> Preregistration:
    d: dict[str, Any] = dict(data)
    d["status"] = PreregistrationStatus(d["status"])
    d["created_at"] = datetime.fromisoformat(d["created_at"])
    d["updated_at"] = datetime.fromisoformat(d["updated_at"])
    for key in (
        "train_period_start",
        "train_period_end",
        "validation_period_start",
        "validation_period_end",
        "locked_test_period_start",
        "locked_test_period_end",
    ):
        d[key] = datetime.fromisoformat(d[key]).date()
    d["alternative_explanations"] = tuple(d.get("alternative_explanations") or ())
    d["secondary_metrics"] = tuple(d.get("secondary_metrics") or ())
    d["parameters"] = tuple(tuple(p) for p in (d.get("parameters") or ()))
    d["allowed_adjustments"] = tuple(d.get("allowed_adjustments") or ())
    d["forbidden_capabilities"] = tuple(d.get("forbidden_capabilities") or ())
    return Preregistration(**d)


class PreregistrationRegistry:
    """JSON Lines形式で追記専用に記録するPreregistration Registry。"""

    def __init__(self, storage_path: Path) -> None:
        self._storage_path = storage_path
        self._storage_path.parent.mkdir(parents=True, exist_ok=True)

    def record(self, preregistration: Preregistration) -> None:
        existing_ids = {p.preregistration_id for p in self.all()}
        if preregistration.preregistration_id in existing_ids:
            raise AppendOnlyViolationError(
                f"preregistration_id={preregistration.preregistration_id} は既に記録されています(上書き不可)"
            )
        line = json.dumps(_preregistration_to_dict(preregistration), ensure_ascii=False)
        with self._storage_path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")

    def all(self) -> list[Preregistration]:
        if not self._storage_path.exists():
            return []
        preregistrations = []
        with self._storage_path.open(encoding="utf-8") as f:
            for raw_line in f:
                line = raw_line.strip()
                if line:
                    preregistrations.append(_preregistration_from_dict(json.loads(line)))
        return preregistrations

    def get(self, preregistration_id: str) -> Preregistration | None:
        for p in self.all():
            if p.preregistration_id == preregistration_id:
                return p
        return None


__all__ = ["PreregistrationRegistry"]
