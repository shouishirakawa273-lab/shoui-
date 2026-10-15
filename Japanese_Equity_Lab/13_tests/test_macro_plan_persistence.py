from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from lib.errors import AppendOnlyViolationError
from lib.evaluation.integrity import compute_record_hash
from lib.macro_experiments.store import MacroPlanStore, plan_from_dict, plan_to_dict, read_plan
from scripts.macro_plan import build_current_plan


def config() -> dict:
    return dict(
        experiment_id="synthetic-plan",
        event_type="CPI",
        dimension="CPI_YOY",
        unit="percent",
        entity_id="US",
        model_version="UNVALIDATED_SYNTHETIC_V1",
        event_ids=["synthetic-event"],
        minimum_samples=1,
        synthetic=True,
        window_start=(datetime.now(UTC) + timedelta(days=10)).isoformat(),
        window_end=(datetime.now(UTC) + timedelta(days=20)).isoformat(),
        contracts=[
            dict(
                evaluation_contract_id="synthetic-contract",
                evaluation_contract_version=1,
                target="CPI_YOY",
                target_period="2099-01",
                actual_truth_description="synthetic first release",
                metric="ABSOLUTE_ERROR",
                evaluable_at_policy="after first release",
                horizon_rule=None,
            )
        ],
    )


def test_lossless_and_duplicate(tmp_path: Path) -> None:
    plan = build_current_plan(config())
    path = tmp_path / "plans.jsonl"
    MacroPlanStore(path).record(plan)
    assert MacroPlanStore(path).get(plan.experiment.experiment_id) == plan
    assert read_plan(path, plan.experiment.experiment_id) == plan
    before = path.read_bytes()
    with pytest.raises(AppendOnlyViolationError):
        MacroPlanStore(path).record(plan)
    assert path.read_bytes() == before


@pytest.mark.parametrize("mutation", ["outer", "nested", "unknown", "missing", "bool", "version", "roster", "policy"])
def test_reject_invalid_plan(mutation: str) -> None:
    data = plan_to_dict(build_current_plan(config()))
    if mutation == "outer":
        data["record_hash"] = "bad"
    elif mutation == "nested":
        data["contracts"][0]["target_period"] = "bad"
    elif mutation == "unknown":
        data["unknown"] = 1
    elif mutation == "missing":
        del data["unit"]
    elif mutation == "bool":
        data["minimum_samples"] = True
    elif mutation == "version":
        data["contracts"][0]["evaluation_contract_version"] = True
    elif mutation == "roster":
        data["event_ids"] = [3]
    else:
        data["experiment"]["execution_policy_reference"] = "CHANGED"
        data["experiment"]["record_hash"] = compute_record_hash(data["experiment"])
        data["record_hash"] = compute_record_hash(data)
    with pytest.raises((ValueError, TypeError)):
        plan_from_dict(data)


@pytest.mark.parametrize(
    "key,value",
    [
        ("created_at", "2000-01-01T00:00:00Z"),
        ("minimum_samples", True),
        ("synthetic", 1),
        ("window_start", "2000-01-01T00:00:00Z"),
    ],
)
def test_config_rejections(key: str, value: object) -> None:
    data = config()
    data[key] = value
    with pytest.raises(ValueError):
        build_current_plan(data)


def test_cli_real_other_cwd(tmp_path: Path) -> None:
    script = Path(__file__).resolve().parents[1] / "scripts" / "macro_plan.py"
    path, source = tmp_path / "nested" / "plan.jsonl", tmp_path / "config.json"
    source.write_text(json.dumps(config()), encoding="utf-8")

    def run(*args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, "-X", "utf8", str(script), *args],
            cwd=tmp_path,
            env=os.environ.copy(),
            capture_output=True,
            text=True,
            encoding="utf-8",
        )

    before = datetime.now(UTC)
    result = run("register", "--input", str(source), "--store", str(path))
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert before <= datetime.fromisoformat(data["experiment"]["created_at"]) <= datetime.now(UTC)
    assert data["contracts"][0]["created_at"] == data["experiment"]["created_at"]
    shown = run("show", "--store", str(path), "--id", "synthetic-plan")
    assert shown.returncode == 0 and json.loads(shown.stdout) == data
    assert run("register", "--input", str(source), "--store", str(path)).returncode != 0
    absent = tmp_path / "never" / "exists.jsonl"
    assert run("show", "--store", str(absent), "--id", "unknown").returncode != 0
    assert not absent.parent.exists()
    assert run("show", "--store", str(path), "--id", "unknown").returncode != 0
    source.write_text('{"experiment_id":"a","experiment_id":"b"}', encoding="utf-8")
    assert run("register", "--input", str(source), "--store", str(path)).returncode != 0


def test_corrupt_store(tmp_path: Path) -> None:
    path = tmp_path / "plan.jsonl"
    data = plan_to_dict(build_current_plan(config()))
    path.write_text(json.dumps(data).replace('"unit": "percent"', '"unit": "percent", "unit": "other"'), encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate JSON key"):
        MacroPlanStore(path).all()
    bad = copy.deepcopy(data)
    bad["contracts"][0]["record_hash"] = "bad"
    path.write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(ValueError, match="integrity"):
        read_plan(path, "synthetic-plan")


@pytest.mark.parametrize("field", sorted(config()))
def test_config_missing_fields(field: str) -> None:
    data = config()
    del data[field]
    with pytest.raises(ValueError):
        build_current_plan(data)


@pytest.mark.parametrize("field", sorted(config()["contracts"][0]))
def test_contract_missing_fields(field: str) -> None:
    data = config()
    del data["contracts"][0][field]
    with pytest.raises(ValueError):
        build_current_plan(data)


def test_contract_no_backdate_and_unknown() -> None:
    for key in ("created_at", "unexpected"):
        data = config()
        data["contracts"][0][key] = "2000-01-01T00:00:00Z"
        with pytest.raises(ValueError):
            build_current_plan(data)


@pytest.mark.parametrize("node", ["experiment", "contract"])
@pytest.mark.parametrize("change", ["unknown", "missing", "wrongtype"])
def test_nested_schema(node: str, change: str) -> None:
    data = plan_to_dict(build_current_plan(config()))
    item = data["experiment"] if node == "experiment" else data["contracts"][0]
    if change == "unknown":
        item["unknown"] = "value"
    elif change == "missing":
        del item["created_at"]
    else:
        item["created_at"] = 3
    with pytest.raises(ValueError):
        plan_from_dict(data)


def test_duplicate_store_records_and_changed_id(tmp_path: Path) -> None:
    path = tmp_path / "plans.jsonl"
    plan = build_current_plan(config())
    MacroPlanStore(path).record(plan)
    alternative = config()
    alternative["model_version"] = "OTHER_SYNTHETIC"
    with pytest.raises(AppendOnlyViolationError):
        MacroPlanStore(path).record(build_current_plan(alternative))
    line = path.read_text(encoding="utf-8")
    path.write_text(line + line, encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate stored"):
        MacroPlanStore(path).all()
    with pytest.raises(ValueError, match="duplicate stored"):
        read_plan(path, "synthetic-plan")


@pytest.mark.parametrize("horizon", [None, "", "   ", "explicit horizon"])
def test_horizon_lossless_store_and_cli(tmp_path: Path, horizon: str | None) -> None:
    data = config()
    data["contracts"][0]["horizon_rule"] = horizon
    plan = build_current_plan(data)
    assert plan_from_dict(plan_to_dict(plan)) == plan
    path = tmp_path / "plans.jsonl"
    MacroPlanStore(path).record(plan)
    assert read_plan(path, plan.experiment.experiment_id) == plan
    source = tmp_path / "config.json"
    source.write_text(json.dumps(data), encoding="utf-8")
    script = Path(__file__).resolve().parents[1] / "scripts" / "macro_plan.py"
    registered_path = tmp_path / "cli.jsonl"
    result = subprocess.run(
        [sys.executable, "-X", "utf8", str(script), "register", "--input", str(source), "--store", str(registered_path)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert result.returncode == 0, result.stderr
    registered = json.loads(result.stdout)
    assert registered["contracts"][0]["horizon_rule"] == horizon
    shown = subprocess.run(
        [sys.executable, "-X", "utf8", str(script), "show", "--store", str(registered_path), "--id", "synthetic-plan"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert shown.returncode == 0, shown.stderr
    assert json.loads(shown.stdout) == registered
