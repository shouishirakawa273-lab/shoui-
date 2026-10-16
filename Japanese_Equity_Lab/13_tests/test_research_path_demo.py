"""Independent arithmetic and provenance checks on the connected synthetic path."""

import json
import subprocess
import sys
from decimal import ROUND_UP, Decimal, Inexact, localcontext
from pathlib import Path

import pytest
from lib.evaluation.integrity import compute_record_hash, to_hashable, verify_record_integrity
from scripts.research_path_demo import run_demo


def test_actual_cross_stage_lineage_and_independent_arithmetic():
    report = run_demo()
    bridge, request = report["bridge"], report["request"]
    baseline, replay = report["valuations"]
    returns, terms = report["returns"], report["shared_terms"]
    assert bridge["request_hash"] == request["record_hash"]
    for valuation, forecast in zip((baseline, replay), (bridge["baseline_forecast"], bridge["replay_forecast"]), strict=True):
        assert valuation["input_forecast_reference"] == forecast["result_id"]
        assert valuation["entity_id"] == request["entity_id"] == terms["price"]["entity_id"]
        assert valuation["evidence_cutoff"] == request["evidence_cutoff"] == report["cutoff"]
        assert valuation["target_period"] == request["forecast_period"] == terms["exit_mapping"]["target_period"]
    assert returns["baseline_hash"] == baseline["record_hash"] == terms["basis"]["baseline_hash"]
    assert returns["replay_hash"] == replay["record_hash"] == terms["basis"]["replay_hash"]
    assert returns["terms_hash"] == compute_record_hash({"terms": terms})
    assert terms["macro_reference"] == bridge["record_hash"]
    assert terms["cash"]["coverage_end"] == request["period_end"] == terms["exit_mapping"]["exit_at"]
    assert Decimal(bridge["baseline_operating_income_jpy"]) == 100
    assert Decimal(bridge["replay_operating_income_jpy"]) == 120
    for side, oi, value in ((baseline, 100, 75), (replay, 120, 91)):
        scenario = next(s for s in side["scenarios"] if s["scenario"] == "BASE")
        assert Decimal(scenario["input_operating_income"]) == oi
        assert Decimal(scenario["estimated_value_per_share"]) == value == (oi * 8 - 50) / 10
    for scenario in ("BULL", "BEAR"):
        assert next(s for s in baseline["scenarios"] if s["scenario"] == scenario) == next(
            s for s in replay["scenarios"] if s["scenario"] == scenario
        )
    base = next(s for s in returns["scenarios"] if s["scenario"] == "BASE")
    with localcontext() as context:
        context.prec = 50
        assert Decimal(base["baseline"]["net_before_tax_return"]) == Decimal(-5) / 81
        assert Decimal(base["replay"]["net_before_tax_return"]) == Decimal(11) / 81
        assert Decimal(base["replay_minus_baseline"]["net_before_tax_return"]) == Decimal(11) / 81 - Decimal(-5) / 81
    assert report["synthetic"] is True and report["empirical_validation"] is False
    assert report["artifact_hash"] == compute_record_hash({k: v for k, v in report.items() if k != "artifact_hash"})
    assert report["rejection"] is None


def test_future_driver_blocks_every_downstream_phase():
    report = run_demo(future_driver=True)
    assert report["rejection"]["phase"] == "EXPOSURE_BRIDGE"
    assert report["rejection"]["reason"]
    for key in ("valuations", "shared_terms", "returns", "multiple", "balance_sheet"):
        assert report[key] is None
    assert report["artifact_hash"] == compute_record_hash({k: v for k, v in report.items() if k != "artifact_hash"})


def test_inputs_unchanged_and_each_intermediate_hash_valid(monkeypatch):
    import scripts.research_path_demo as demo

    request = demo.synthetic_bridge_request()
    before = to_hashable(request)
    monkeypatch.setattr(demo, "synthetic_bridge_request", lambda **kwargs: request)
    report = demo.run_demo()
    assert to_hashable(request) == before and verify_record_integrity(request)
    records = [
        report["bridge"],
        *report["valuations"],
        report["returns"],
        report["bridge"]["baseline_forecast"],
        report["bridge"]["replay_forecast"],
    ]
    for record in records:
        assert record["record_hash"] == compute_record_hash(record)


@pytest.mark.parametrize("precision", [3, 80])
def test_all_phases_context_invariant(precision):
    expected = run_demo()
    with localcontext() as context:
        context.prec, context.rounding, context.Emin, context.Emax = precision, ROUND_UP, -5, 5
        context.traps[Inexact] = True
        context.flags[Inexact] = True
        before = context.copy()
        assert run_demo() == expected
        assert context.prec == before.prec and context.rounding == before.rounding
        assert context.Emin == before.Emin and context.Emax == before.Emax
        assert context.traps == before.traps and context.flags == before.flags


@pytest.mark.parametrize("future_driver", [False, True])
def test_cli_separate_process_and_different_cwd(tmp_path, future_driver):
    script = Path(__file__).resolve().parents[1] / "scripts" / "research_path_demo.py"
    args = [sys.executable, str(script)] + (["--future-driver"] if future_driver else [])
    first = subprocess.run(args, cwd=script.parent, check=True, capture_output=True, text=True)
    second = subprocess.run(args, cwd=tmp_path, check=True, capture_output=True, text=True)
    assert first.stderr == second.stderr == ""
    assert json.loads(first.stdout) == json.loads(second.stdout) == run_demo(future_driver=future_driver)
