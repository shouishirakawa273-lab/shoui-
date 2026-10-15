"""Strict plan persistence. Local single-writer use; no concurrent transaction guarantee."""

from __future__ import annotations

import json
from dataclasses import fields
from datetime import datetime
from pathlib import Path
from typing import Any

from lib.evaluation.integrity import to_hashable, verify_record_integrity
from lib.evaluation.model import EvaluationContract, EvaluationMetric, ExperimentSpec
from lib.evaluation.store import AppendOnlyRecordStore
from lib.macro_experiments.comparison import RegisteredMacroPlan, register_macro_plan


def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def strict_object(value: Any, names: set[str]) -> dict[str, Any]:
    if type(value) is not dict or set(value) != names:
        raise ValueError(f"expected exact fields: {sorted(names)}")
    return value


def timestamp(value: Any) -> datetime:
    if type(value) is not str:
        raise ValueError("timestamp must be ISO string")
    result = datetime.fromisoformat(value)
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError("timezone-aware timestamp required")
    return result


def strings(value: Any) -> tuple[str, ...]:
    if type(value) is not list or any(type(x) is not str or not x.strip() for x in value):
        raise ValueError("expected array of nonempty strings")
    return tuple(value)


def _decode_record(data: Any, cls: type[Any]) -> Any:
    raw = strict_object(data, {f.name for f in fields(cls)})
    values: dict[str, Any] = {}
    for key, value in raw.items():
        if key in {"created_at", "evaluation_window_start", "evaluation_window_end"}:
            values[key] = timestamp(value)
        elif key in {"evaluation_contract_ids", "variant_ids"}:
            values[key] = strings(value)
        elif key == "evaluation_contract_version":
            if type(value) is not int:
                raise ValueError("contract version must be integer")
            values[key] = value
        elif key == "horizon_rule" and value is None:
            values[key] = None
        else:
            if type(value) is not str or not value.strip():
                raise ValueError(f"{key} must be nonempty string")
            values[key] = EvaluationMetric(value) if key == "metric" else value
    record = cls(**values)
    if not verify_record_integrity(record):
        raise ValueError("nested record integrity failure")
    return record


def plan_from_dict(data: Any) -> RegisteredMacroPlan:
    raw = strict_object(data, {f.name for f in fields(RegisteredMacroPlan)})
    experiment = _decode_record(raw["experiment"], ExperimentSpec)
    if type(raw["contracts"]) is not list:
        raise ValueError("contracts must be array")
    contracts = tuple(_decode_record(c, EvaluationContract) for c in raw["contracts"])
    values = {k: v for k, v in raw.items() if k not in {"experiment", "contracts", "event_ids"}}
    for key, value in values.items():
        expected = bool if key == "synthetic" else int if key == "minimum_samples" else str
        if type(value) is not expected or (isinstance(value, str) and not value.strip()):
            raise ValueError(f"invalid type/value: {key}")
    plan = RegisteredMacroPlan(experiment=experiment, contracts=contracts, event_ids=strings(raw["event_ids"]), **values)
    if not verify_record_integrity(plan):
        raise ValueError("plan integrity failure")
    if experiment.evaluation_window_start is None or experiment.evaluation_window_end is None:
        raise ValueError("evaluation window required")
    canonical = register_macro_plan(
        experiment_id=experiment.experiment_id,
        event_type=plan.event_type,
        dimension=plan.dimension,
        unit=plan.unit,
        entity_id=plan.entity_id,
        model_version=plan.model_version,
        event_ids=plan.event_ids,
        contracts=plan.contracts,
        minimum_samples=plan.minimum_samples,
        synthetic=plan.synthetic,
        registered_at=experiment.created_at,
        window_start=experiment.evaluation_window_start,
        window_end=experiment.evaluation_window_end,
    )
    if canonical != plan:
        raise ValueError("noncanonical registered plan")
    return plan


def plan_to_dict(plan: RegisteredMacroPlan) -> dict[str, Any]:
    data = to_hashable(plan)
    if not isinstance(data, dict):
        raise ValueError("plan encoding must be object")
    plan_from_dict(data)
    return data


class MacroPlanStore(AppendOnlyRecordStore[RegisteredMacroPlan]):
    """D0107 append-only writes, strict JSON reads. Same ID always rejected."""

    def __init__(self, storage_path: Path) -> None:
        super().__init__(storage_path, id_of=lambda p: p.experiment.experiment_id, to_dict=plan_to_dict, from_dict=plan_from_dict)

    def all(self) -> list[RegisteredMacroPlan]:
        if not self._storage_path.exists():
            return []
        with self._storage_path.open(encoding="utf-8") as stream:
            plans = [plan_from_dict(json.loads(line, object_pairs_hook=unique_object)) for line in stream if line.strip()]
        ids = [p.experiment.experiment_id for p in plans]
        if len(set(ids)) != len(ids):
            raise ValueError("duplicate stored experiment ID")
        return plans


def read_plan(storage_path: Path, experiment_id: str) -> RegisteredMacroPlan:
    """Read without constructing the mkdir-producing D0107 store."""
    if not storage_path.is_file():
        raise ValueError("plan store does not exist")
    with storage_path.open(encoding="utf-8") as stream:
        plans = [plan_from_dict(json.loads(line, object_pairs_hook=unique_object)) for line in stream if line.strip()]
    ids = [p.experiment.experiment_id for p in plans]
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate stored experiment ID")
    for plan in plans:
        if plan.experiment.experiment_id == experiment_id:
            return plan
    raise ValueError("unknown experiment ID")
