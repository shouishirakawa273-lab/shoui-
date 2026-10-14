"""Read-only preflight rejects tampering without claiming calculator acceptance."""

import json
import os
import subprocess
import sys
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from lib.evaluation.integrity import to_hashable
from lib.profit_impact.model import Applicability, Direction, ImpactSchemaError
from lib.profit_impact.preflight import decode_request, inspect_request
from test_profit_impact import change, request, source, with_source


def test_raw_hash_rejected_before_constructor_repair() -> None:
    data = to_hashable(request())
    data["disclosures"][0]["scope"] = "UNKNOWN"
    with pytest.raises(ImpactSchemaError, match="integrity"):
        decode_request(json.dumps(data))


@pytest.mark.parametrize("text", ['{"x":1,"x":2}', '{"x":NaN}', '{"x":Infinity}', '{"x":-Infinity}'])
def test_noncanonical_json_rejected(text: str) -> None:
    with pytest.raises(ValueError):
        decode_request(text)


def test_unknown_direction_does_not_mean_observed_time_invalid() -> None:
    req = with_source(request(), source(direction=Direction.UNKNOWN, direction_basis=None))
    report = inspect_request(decode_request(json.dumps(to_hashable(req))))
    findings = report["findings"]
    assert {"scope": "SIGNED_DELTA", "code": "DIRECTION_UNKNOWN", "disclosure_id": "SOURCE_COPPER"} in findings
    assert not any(f["code"] == "SYSTEM_OBSERVED_AVAILABILITY_UNCONFIRMED" for f in findings)
    assert report["calculation_status"] == "NOT_EVALUATED"
    assert report["original_source_bytes_verified"] == "NOT_CHECKED"


def test_archive_identity_and_mixed_record_only_blocked() -> None:
    req = change(request(), record_only=True)
    req = change(req, disclosures=(replace(req.disclosures[0], entity_id="OTHER", record_hash=""),))
    report = inspect_request(req)
    assert report["archive_status"] == "BLOCKED"
    codes = {f["code"] for f in report["findings"]}
    assert {"RECORD_ONLY_HAS_CALCULATION_INPUTS", "DISCLOSURE_IDENTITY_MISMATCH"} <= codes


def test_deterministic_report_and_cli_does_not_modify_input(tmp_path: Path) -> None:
    req = request()
    path = tmp_path / "request.json"
    original = json.dumps(to_hashable(req)).encode()
    path.write_bytes(original)
    script = Path(__file__).resolve().parents[1] / "scripts" / "profit_impact_preflight.py"
    env = {key: value for key, value in os.environ.items() if key != "PYTHONDONTWRITEBYTECODE"}
    package = script.parents[1] / "lib"
    bytecode_before = {p: p.stat().st_mtime_ns for p in package.rglob("*.pyc")}
    result = subprocess.run([sys.executable, str(script), str(path)], capture_output=True, text=True, env=env, check=False)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == inspect_request(req) == inspect_request(req)
    assert path.read_bytes() == original
    assert list(tmp_path.iterdir()) == [path]
    assert {p: p.stat().st_mtime_ns for p in package.rglob("*.pyc")} == bytecode_before


@pytest.mark.parametrize("collection", ["artifacts", "disclosures", "sensitivities", "shocks"])
def test_duplicate_component_identifiers_block_archive(collection: str) -> None:
    req = request()
    values = getattr(req, collection)
    report = inspect_request(change(req, **{collection: (*values, *values)}))
    assert report["archive_status"] == "BLOCKED"
    assert any(f["code"].startswith("DUPLICATE_") for f in report["findings"])


def test_source_claims_are_preserved_without_truth_upgrade() -> None:
    req = with_source(request(), source(direction=Direction.UNKNOWN, direction_basis=None))
    report = inspect_request(req)
    claim = report["source_claims"][0]
    assert claim["direction"] == "UNKNOWN"
    assert claim["limitations"] == req.disclosures[0].limitations
    assert claim["declared_values_verified"] is True
    assert report["source_semantic_truth"] == "NOT_CHECKED_CALLER_DECLARATIONS_ONLY"


def test_missing_artifact_blocks_archive() -> None:
    assert inspect_request(change(request(), artifacts=()))["archive_status"] == "BLOCKED"


def test_disclosed_unit_and_time_failures_are_reported_without_outputs() -> None:
    req = request()
    shock = replace(req.shocks[0], change=Decimal("30"), available_at=req.created_at + timedelta(days=1))
    report = inspect_request(change(req, shocks=(shock,)))
    codes = {f["code"] for f in report["findings"]}
    assert {"SHOCK_OUTSIDE_DISCLOSED_UNIT", "SHOCK_CHRONOLOGY_INVALID"} <= codes
    assert not {"signed_delta_jpy", "conditional_target_pretax_jpy", "magnitude_delta_jpy"}.intersection(report)


def test_verified_range_requires_absolute_levels() -> None:
    src = source(
        applicability=Applicability.VERIFIED_LINEAR_RANGE,
        minimum_level=Decimal("90"),
        maximum_level=Decimal("120"),
    )
    req = with_source(request(), src)
    req = change(req, shocks=(replace(req.shocks[0], baseline_level=None, scenario_level=None),))
    assert "ABSOLUTE_DRIVER_LEVELS_MISSING" in {f["code"] for f in inspect_request(req)["findings"]}


def test_cli_invalid_payload_is_not_echoed(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text('{"private_marker":"do_not_echo","private_marker":2}', encoding="utf-8")
    script = Path(__file__).resolve().parents[1] / "scripts" / "profit_impact_preflight.py"
    result = subprocess.run(
        [sys.executable, str(script), str(path)],
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        check=False,
    )
    assert result.returncode == 2
    assert "private_marker" not in result.stdout and "do_not_echo" not in result.stdout
    assert not result.stdout
    assert json.loads(result.stderr)["input_status"] == "INVALID"
