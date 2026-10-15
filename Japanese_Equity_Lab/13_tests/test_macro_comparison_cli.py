"""External record boundary and read-only comparison operation."""

from __future__ import annotations

import copy
import json
import subprocess
import sys
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from lib.evaluation.integrity import compute_record_hash, to_hashable
from lib.evaluation.model import BullBaseBearForecast, ForecastShape, ThesisImpactReference
from lib.evidence.thesis_impact import ThesisScenario
from lib.macro_experiments.comparison import compare_macro_forecasts
from lib.macro_experiments.input import read_samples, samples_from_dict
from lib.macro_experiments.store import MacroPlanStore
from test_macro_experiments import fixture, rehash

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "macro_compare.py"


def payload(sample):
    return {"schema_version": 1, "samples": [to_hashable(sample)]}


def invoke(tmp_path, data, *, plan=None, store=None):
    if plan is None:
        plan, _ = fixture()
    if store is None:
        store = tmp_path / "plans.jsonl"
        MacroPlanStore(store).record(plan)
    source = tmp_path / "samples.json"
    source.write_text(json.dumps(data), encoding="utf-8")
    before = source.read_bytes(), store.read_bytes() if store.exists() else None
    run = subprocess.run(
        [sys.executable, str(SCRIPT), "--store", str(store), "--id", "x", "--input", str(source)],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        check=False,
    )
    assert before == (source.read_bytes(), store.read_bytes() if store.exists() else None)
    return run


def test_complete_pair_and_result_hash_actual_time(tmp_path):
    _, sample = fixture()
    before = datetime.now(UTC)
    run = invoke(tmp_path, payload(sample))
    after = datetime.now(UTC)
    assert run.returncode == 0 and not run.stderr
    result = json.loads(run.stdout)
    assert result["status"] == "DESCRIPTIVE_ONLY"
    assert result["own_mae"] == "0.1" and result["consensus_mae"] == "0.2"
    assert result["record_hash"] == compute_record_hash(result)
    assert before <= datetime.fromisoformat(result["evaluated_at"]) <= after
    assert result["samples"][0]["own_evaluation"]["actual_reference"] == "r"
    assert result["calculation_contract_version"]
    assert "NOT_INDEPENDENTLY_VERIFIED" in result["provenance_label"]
    assert "NO_PROMOTION" in result["interpretation"]


@pytest.mark.parametrize("missing", ["consensus", "release", "prediction", "snapshot"])
def test_nullable_records_are_reported_not_discarded(tmp_path, missing):
    _, sample = fixture()
    data = payload(sample)
    data["samples"][0][missing] = None
    run = invoke(tmp_path, data)
    assert run.returncode == 0
    result = json.loads(run.stdout)
    assert result["status"] == "INSUFFICIENT_HISTORY"
    assert f"MISSING_{missing.upper()}" in result["samples"][0]["reasons"]
    assert result["expected_samples"] == 1 and result["paired_samples"] == 0


@pytest.mark.parametrize("mode", ["empty", "duplicate", "pit", "future"])
def test_api_reasons_survive_cli(tmp_path, mode):
    plan, sample = fixture()
    if mode == "pit":
        sample = replace(sample, prediction=rehash(sample.prediction, evidence_cutoff=sample.release.actual_public_at))
    if mode == "future":
        sample = replace(sample, release=rehash(sample.release, available_at=datetime.now(UTC) + timedelta(days=1)))
    data = payload(sample)
    if mode == "empty":
        data["samples"] = []
    if mode == "duplicate":
        data["samples"] *= 2
    expected = compare_macro_forecasts(plan=plan, samples=samples_from_dict(data), evaluated_at=datetime.now(UTC))
    run = invoke(tmp_path, data)
    assert run.returncode == 0
    result = json.loads(run.stdout)
    assert result["status"] == expected.status == "INSUFFICIENT_HISTORY"
    assert result["samples"][0]["reasons"] == list(expected.samples[0].reasons)


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("schema_version",), True),
        (("schema_version",), "1"),
        (("samples",), {}),
        (("samples", 0, "synthetic"), 1),
        (("samples", 0, "event"), None),
        (("samples", 0, "event", "event_version"), True),
        (("samples", 0, "event", "event_id"), 12),
        (("samples", 0, "event", "scheduled_at"), "2026-01-01T00:00:00"),
        (("samples", 0, "event", "record_hash"), "tampered"),
        (("samples", 0, "consensus", "estimate_count"), "3"),
        (("samples", 0, "consensus", "dispersion"), "NaN"),
        (("samples", 0, "release", "actual_first_release"), 3.3),
        (("samples", 0, "release", "previous_as_published"), "Infinity"),
        (("samples", 0, "prediction", "forecast_shape"), "UNKNOWN"),
        (("samples", 0, "prediction", "scalar_forecast", "value"), "sNaN"),
        (("samples", 0, "prediction", "scalar_forecast", "unit"), False),
        (("samples", 0, "prediction", "bull_base_bear_forecast"), {"bull": "1"}),
        (("samples", 0, "prediction", "target_resolution_at"), 1),
        (("samples", 0, "snapshot", "research_artifact_version"), True),
        (("samples", 0, "snapshot", "evidence_ids"), [1]),
        (("samples", 0, "snapshot", "thesis_impact_references"), [{"research_node_id": "n"}]),
    ],
)
def test_invalid_wire_types_and_hash_fail_closed(tmp_path, path, value):
    _, sample = fixture()
    data = payload(sample)
    cursor = data
    for key in path[:-1]:
        cursor = cursor[key]
    cursor[path[-1]] = value
    run = invoke(tmp_path, data)
    assert run.returncode != 0 and not run.stdout and run.stderr


@pytest.mark.parametrize("level", ["root", "sample", "event", "scalar", "snapshot"])
@pytest.mark.parametrize("operation", ["unknown", "missing"])
def test_exact_fields_every_level(level, operation):
    _, sample = fixture()
    data = payload(sample)
    targets = {
        "root": data,
        "sample": data["samples"][0],
        "event": data["samples"][0]["event"],
        "scalar": data["samples"][0]["prediction"]["scalar_forecast"],
        "snapshot": data["samples"][0]["snapshot"],
    }
    target = targets[level]
    if operation == "unknown":
        target["extra"] = None
    else:
        del target[next(iter(target))]
    with pytest.raises(ValueError):
        samples_from_dict(data)


def test_duplicate_json_keys_nested_and_root(tmp_path):
    _, sample = fixture()
    text = json.dumps(payload(sample))
    for corrupted in (
        text.replace('"schema_version": 1', '"schema_version": 1, "schema_version": 1'),
        text.replace('"event_version": 1', '"event_version": 1, "event_version": 1'),
    ):
        source = tmp_path / "duplicate.json"
        source.write_text(corrupted, encoding="utf-8")
        with pytest.raises(ValueError, match="duplicate JSON key"):
            read_samples(source)


@pytest.mark.parametrize("value", [None, "", "  ", "v1"])
def test_optional_strings_roundtrip_without_loss(value):
    _, sample = fixture()
    sample = replace(
        sample,
        consensus=rehash(sample.consensus, provider_version=value),
        release=rehash(sample.release, source_version=value),
        prediction=rehash(sample.prediction, prompt_version=value, parent_prediction_id=value),
    )
    original = payload(sample)
    snapshot = copy.deepcopy(original)
    assert samples_from_dict(original) == (sample,)
    assert original == snapshot


def test_unknown_store_path_and_unknown_id_never_create(tmp_path):
    _, sample = fixture()
    missing = tmp_path / "missing" / "plans.jsonl"
    run = invoke(tmp_path, payload(sample), store=missing)
    assert run.returncode != 0 and not run.stdout and not missing.parent.exists()
    plan, _ = fixture()
    store = tmp_path / "plans.jsonl"
    MacroPlanStore(store).record(rehash(plan, experiment=rehash(plan.experiment, experiment_id="other")))
    run = invoke(tmp_path, payload(sample), store=store)
    assert run.returncode != 0 and not run.stdout


def test_all_optional_nested_fields_roundtrip_and_validate():
    _, sample = fixture()
    sample = replace(
        sample,
        consensus=rehash(sample.consensus, estimate_count=3, dispersion=Decimal("0.1")),
        release=rehash(sample.release, previous_as_published=Decimal("3.0")),
        prediction=rehash(
            sample.prediction,
            scalar_forecast=None,
            forecast_shape=ForecastShape.BULL_BASE_BEAR,
            bull_base_bear_forecast=BullBaseBearForecast(bull=Decimal("4"), base=Decimal("3"), bear=Decimal("2"), unit="PERCENT"),
            target_resolution_at=sample.release.actual_public_at,
        ),
        snapshot=rehash(
            sample.snapshot,
            evidence_ids=("a", "b"),
            thesis_impact_references=(
                ThesisImpactReference(research_node_id="n", scenario=next(iter(ThesisScenario)), evidence_id="a"),
            ),
        ),
    )
    data = payload(sample)
    assert samples_from_dict(data) == (sample,)
    for path, value in [
        (("prediction", "bull_base_bear_forecast", "bull"), "-Infinity"),
        (("snapshot", "thesis_impact_references", 0, "scenario"), "UNKNOWN"),
        (("snapshot", "thesis_impact_references", 0, "evidence_id"), 1),
    ]:
        invalid = copy.deepcopy(data)
        cursor = invalid["samples"][0]
        for key in path[:-1]:
            cursor = cursor[key]
        cursor[path[-1]] = value
        with pytest.raises(ValueError):
            samples_from_dict(invalid)
