"""Explicit macro plan registration (current UTC only) and read-only inspection."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib.errors import AppendOnlyViolationError  # noqa: E402
from lib.evaluation.model import EvaluationMetric, build_evaluation_contract  # noqa: E402
from lib.macro_experiments.comparison import RegisteredMacroPlan, register_macro_plan  # noqa: E402
from lib.macro_experiments.store import (  # noqa: E402
    MacroPlanStore,
    plan_to_dict,
    read_plan,
    strict_object,
    strings,
    timestamp,
    unique_object,
)

CONFIG_FIELDS = {
    "experiment_id",
    "event_type",
    "dimension",
    "unit",
    "entity_id",
    "model_version",
    "event_ids",
    "contracts",
    "minimum_samples",
    "synthetic",
    "window_start",
    "window_end",
}
CONTRACT_FIELDS = {
    "evaluation_contract_id",
    "evaluation_contract_version",
    "target",
    "target_period",
    "actual_truth_description",
    "metric",
    "evaluable_at_policy",
    "horizon_rule",
}


def build_current_plan(data: Any) -> RegisteredMacroPlan:
    raw = strict_object(data, CONFIG_FIELDS)
    now = datetime.now(UTC)
    for key in CONFIG_FIELDS - {"event_ids", "contracts", "minimum_samples", "synthetic"}:
        if type(raw[key]) is not str or not raw[key].strip():
            raise ValueError(f"{key} must be nonempty string")
    if type(raw["minimum_samples"]) is not int or type(raw["synthetic"]) is not bool:
        raise ValueError("explicit integer minimum_samples and boolean synthetic required")
    if type(raw["contracts"]) is not list:
        raise ValueError("contracts must be array")
    contracts = []
    for value in raw["contracts"]:
        contract = strict_object(value, CONTRACT_FIELDS)
        for key in CONTRACT_FIELDS - {"evaluation_contract_version", "horizon_rule"}:
            if type(contract[key]) is not str or not contract[key].strip():
                raise ValueError(f"contract {key} must be nonempty string")
        if type(contract["evaluation_contract_version"]) is not int:
            raise ValueError("contract version must be integer")
        if contract["horizon_rule"] is not None and type(contract["horizon_rule"]) is not str:
            raise ValueError("horizon_rule must be string or null")
        kwargs = dict(contract)
        kwargs["metric"] = EvaluationMetric(contract["metric"])
        contracts.append(build_evaluation_contract(**kwargs, created_at=now))
    return register_macro_plan(
        experiment_id=raw["experiment_id"],
        event_type=raw["event_type"],
        dimension=raw["dimension"],
        unit=raw["unit"],
        entity_id=raw["entity_id"],
        model_version=raw["model_version"],
        event_ids=strings(raw["event_ids"]),
        contracts=tuple(contracts),
        minimum_samples=raw["minimum_samples"],
        synthetic=raw["synthetic"],
        registered_at=now,
        window_start=timestamp(raw["window_start"]),
        window_end=timestamp(raw["window_end"]),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    register = commands.add_parser("register")
    register.add_argument("--input", required=True, type=Path)
    register.add_argument("--store", required=True, type=Path)
    show = commands.add_parser("show")
    show.add_argument("--store", required=True, type=Path)
    show.add_argument("--id", required=True)
    args = parser.parse_args()
    try:
        if args.command == "register":
            with args.input.open(encoding="utf-8") as stream:
                plan = build_current_plan(json.load(stream, object_pairs_hook=unique_object))
            MacroPlanStore(args.store).record(plan)
        else:
            plan = read_plan(args.store, args.id)
        sys.stdout.write(json.dumps(plan_to_dict(plan), ensure_ascii=False, sort_keys=True) + "\n")
    except (ValueError, TypeError, KeyError, OSError, AppendOnlyViolationError) as exc:
        logging.error("macro plan: %s", exc)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
