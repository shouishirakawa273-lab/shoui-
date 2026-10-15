"""Whole D0110 synthetic walkthrough plus isolated refusal paths."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from decimal import Decimal
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "d0110_demo.py"
SPEC = importlib.util.spec_from_file_location("d0110_demo", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
DEMO = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(DEMO)


def test_synthetic_whole_flow_and_separated_assumptions():
    result = DEMO.run_demo()
    assert result["synthetic"] is True and result["empirical_certified"] is False
    assert result["d0110_1"]["status"] == "SUCCESS"
    assert result["d0110_1"]["surprise"]["surprise_value"] == "0.2"
    assert result["d0110_2"]["response"]["status"] == "SUCCESS"
    assert Decimal(result["d0110_2"]["response"]["change_value"]) == Decimal("1.5")
    assert result["d0110_2"]["response"]["non_causal_label"] == "OBSERVED_ASSOCIATION_ONLY"
    assert result["d0110_2"]["link"]["status"] == "SUCCESS"
    bridge = result["d0110_3"]["bridge"]
    assert bridge["status"] == "SUCCESS"
    assert Decimal(bridge["baseline_operating_income_jpy"]) == Decimal("100")
    assert Decimal(bridge["replay_operating_income_jpy"]) == Decimal("120")
    values = result["d0110_3"]["valuations"]
    selected = [next(s for s in v["scenarios"] if s["scenario"] == "BASE") for v in values]
    assert [Decimal(s["estimated_value_per_share"]) for s in selected] == [Decimal("75"), Decimal("91")]
    comparison = result["d0110_4"]
    assert comparison["status"] == "INSUFFICIENT_HISTORY" and comparison["paired_samples"] == 1
    assert comparison["own_minus_consensus_mae"] == "-0.1"
    assert comparison["samples"][0]["consensus_audit_snapshot"]["research_schema_version"] == (
        "DERIVED_CONSENSUS_AUDIT_REFERENCE_V1"
    )
    assert any("independently injected" in s for s in result["limitations"])
    assert result == DEMO.run_demo()


@pytest.mark.parametrize("option", ["future_consensus", "future_post", "future_driver"])
def test_each_future_input_refuses_its_own_path(option):
    result = DEMO.run_demo(**{option: True})
    if option == "future_consensus":
        assert result["d0110_1"]["status"] == "PIT_INVALID"
        assert result["d0110_1"]["surprise"] is None and result["d0110_2"]["link"] is None
        assert result["d0110_4"]["paired_samples"] == 0
    elif option == "future_post":
        assert result["d0110_2"]["response"]["status"] != "SUCCESS"
        assert result["d0110_3"]["bridge"]["status"] == "SUCCESS"
    else:
        assert result["d0110_3"]["bridge"]["status"] == "PIT_INVALID"
        assert result["d0110_3"]["valuations"] == []


def test_cli_matches_library_from_other_working_directory(tmp_path):
    completed = subprocess.run([sys.executable, str(SCRIPT)], cwd=tmp_path, capture_output=True, text=True, check=False)
    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout) == DEMO.run_demo()
