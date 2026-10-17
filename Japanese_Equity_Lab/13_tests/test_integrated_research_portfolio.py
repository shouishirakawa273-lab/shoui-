"""Connected typed handoffs, independent arithmetic, refusals and full JSON reproduction."""

import json
import subprocess
import sys
from decimal import ROUND_UP, Decimal, Inexact, localcontext
from fractions import Fraction
from pathlib import Path

import pytest
from lib.evaluation.integrity import compute_record_hash, to_hashable

from scripts import integrated_research_portfolio_demo as demo

D = Decimal


def test_actual_typed_stage_identity_and_input_immutability(monkeypatch):
    calls = {}
    for name in (
        "synthetic_bridge_request",
        "compute_exposure_bridge",
        "evaluate_forward_valuation",
        "compare_scenario_returns",
        "make_request",
        "evaluate_portfolio_risk",
        "make_construction_request",
        "construct_portfolio",
    ):
        original = getattr(demo, name)

        def capture(*args, _original=original, _name=name, **kwargs):
            before = to_hashable((args, kwargs))
            value = _original(*args, **kwargs)
            assert before == to_hashable((args, kwargs))
            calls.setdefault(_name, []).append((args, kwargs, value))
            return value

        monkeypatch.setattr(demo, name, capture)
    report = demo.run_demo()
    request = calls["synthetic_bridge_request"][0][2]
    bridge_args, _, bridge = calls["compute_exposure_bridge"][0]
    assert bridge_args[0] is request
    for call, forecast in zip(
        calls["evaluate_forward_valuation"], (bridge.baseline_forecast, bridge.replay_forecast), strict=True
    ):
        assert call[0][0] is forecast
    _, args, returns = calls["compare_scenario_returns"][0]
    assert args["baseline"] is calls["evaluate_forward_valuation"][0][2]
    assert args["replay"] is calls["evaluate_forward_valuation"][1][2]
    _, portfolio_args, desired = calls["make_request"][0]
    assert portfolio_args["positions"][0].comparison is returns
    assert calls["evaluate_portfolio_risk"][0][0][0] is desired
    assert calls["make_construction_request"][0][1]["desired"] is desired
    construction = calls["make_construction_request"][0][2]
    assert calls["construct_portfolio"][0][0][0] is construction
    assert report["rejection"] is None


def test_independent_all_scenario_returns_allocations_and_lineage():
    report = demo.run_demo()
    bridge, valuations, returns = report["bridge"], report["valuations"], report["returns"]
    desired, construction = report["desired_request"], report["construction_result"]
    final = construction["output_risk"]
    assert len(report["desired_risk"]["breaches"]) == 2
    assert construction["audit"][0]["allocated_weight"] == "0.5"
    assert Decimal(construction["released_cash"]) == D("0.3")
    assert construction["output_request"]["cash_weight"] == "0.5"
    assert final["declared_constraints_pass"] is True and final["breaches"] == []
    assert final["unsupported_checks"]
    for side, forecast in zip(valuations, (bridge["baseline_forecast"], bridge["replay_forecast"]), strict=True):
        assert side["input_forecast_reference"] == forecast["result_id"]
        assert side["entity_id"] == report["request"]["entity_id"]
    assert returns["baseline_hash"] == valuations[0]["record_hash"]
    assert returns["replay_hash"] == valuations[1]["record_hash"]
    assert desired["joint_comparison_hashes"] == [returns["record_hash"]]
    assert desired["record_hash"] in construction["output_request"]["joint_scenario_ref"]
    assert construction["output_request"]["joint_scenario_available_at"] == desired["joint_scenario_available_at"]
    assert construction["output_request"]["positions"][0]["comparison"] == returns
    with localcontext() as context:
        context.prec = 50
        for constituent in returns["scenarios"]:
            scenario = constituent["scenario"]
            for side, key in (("baseline", "baseline_net_return"), ("replay", "replay_net_return")):
                valuation = next(s for s in valuations[0 if side == "baseline" else 1]["scenarios"] if s["scenario"] == scenario)
                value = D(valuation["estimated_value_per_share"])
                independent = (value + D(3) - D(2) - D(80) - D(1)) / D(81)
                assert D(constituent[side]["net_before_tax_return"]) == independent
                for risk, weight in ((report["desired_risk"], Fraction(4, 5)), (final, Fraction(1, 2))):
                    output = next(s for s in risk["scenarios"] if s["scenario"] == scenario)
                    exact = weight * Fraction(independent)
                    expected = D(exact.numerator) / D(exact.denominator)
                    assert abs(D(output[key]) - expected) <= D("1e-49")
        base = next(s for s in returns["scenarios"] if s["scenario"] == "BASE")
        assert D(base["baseline"]["net_before_tax_return"]) == D(-5) / 81
        assert D(base["replay"]["net_before_tax_return"]) == D(11) / 81
    output_request = construction["output_request"]
    assert (
        sum((Fraction(D(p["capital_weight"])) for p in output_request["positions"]), Fraction(D(output_request["cash_weight"])))
        == 1
    )
    assert report["product_acceptance"] is report["empirical_validation"] is False


def test_every_nested_record_hash_and_artifact_hash():
    report = demo.run_demo()

    def walk(value):
        if isinstance(value, dict):
            if "record_hash" in value:
                assert value["record_hash"] == compute_record_hash(value)
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(report)
    assert report["artifact_hash"] == compute_record_hash({k: v for k, v in report.items() if k != "artifact_hash"})


@pytest.mark.parametrize("case", ["future_driver", "bad_joint_binding"])
def test_rejection_prevents_construction(monkeypatch, case):
    def prohibited(*args, **kwargs):
        pytest.fail("construction must not run following upstream rejection")

    monkeypatch.setattr(demo, "construct_portfolio", prohibited)
    monkeypatch.setattr(demo, "make_construction_request", prohibited)
    if case == "future_driver":
        monkeypatch.setattr(demo, "evaluate_forward_valuation", prohibited)
    report = demo.run_demo(**{case: True})
    assert report["rejection"]["phase"] == ("EXPOSURE_BRIDGE" if case == "future_driver" else "PORTFOLIO_RISK")
    assert report["rejection"]["reason"]
    assert report["construction_result"] is report["construction_request"] is report["desired_risk"] is None
    if case == "future_driver":
        assert all(report[k] is None for k in ("valuations", "returns", "shared_terms", "desired_request"))
    else:
        assert report["valuations"] and report["returns"] and report["desired_request"]


@pytest.mark.parametrize("flag", [None, "future_driver", "bad_joint_binding"])
def test_context_and_separate_process_cwd(tmp_path, flag):
    options = {} if flag is None else {flag: True}
    expected = demo.run_demo(**options)
    for precision in (3, 80):
        with localcontext() as context:
            context.prec, context.rounding, context.Emin, context.Emax = precision, ROUND_UP, -5, 5
            context.traps[Inexact] = context.flags[Inexact] = True
            before = context.copy()
            assert demo.run_demo(**options) == expected
            assert context.prec == before.prec and context.rounding == before.rounding
            assert context.flags == before.flags and context.traps == before.traps
    script = Path(demo.__file__).resolve()
    args = [sys.executable, str(script)] + ([] if flag is None else ["--" + flag.replace("_", "-")])
    first = subprocess.run(args, cwd=script.parent, capture_output=True, text=True, check=True)
    second = subprocess.run(args, cwd=tmp_path, capture_output=True, text=True, check=True)
    assert first.stderr == second.stderr == ""
    assert json.loads(first.stdout) == json.loads(second.stdout) == expected
